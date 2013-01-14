#!/usr/bin/env python
import os
import re
import sys
import pipes
import shutil
import fnmatch
import tempfile
import subprocess
import multiprocessing
import shlex
import signal
import mutagen.flac
import tagging

encoders = {
    '320':  {'enc': 'lame',     'opts': '-b 320 --ignore-tag-errors'},
    'V0':   {'enc': 'lame',     'opts': '-V 0 --vbr-new --ignore-tag-errors'},
    'V2':   {'enc': 'lame',     'opts': '-V 2 --vbr-new --ignore-tag-errors'},
    'FLAC': {'enc': 'flac',     'opts': '--best'}
}

class TranscodeException(Exception):
    pass

# In most Unix shells, pipelines only report the return code of the
# last process. We need to know if any process in the transcode
# pipeline fails, not just the last one.
#
# This function constructs a pipeline of processes from a chain of
# commands just like a shell does, but it returns the status code (and
# stderr) of every process in the pipeline, not just the last one. The
# results are returned as a list of (code, stderr) pairs, one pair per
# process.
def run_pipeline(cmds):
    # The Python executable (and its children) ignore SIGPIPE. (See
    # http://bugs.python.org/issue1652) Our subprocesses need to see
    # it.
    sigpipe_handler = signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    stdin = None
    last_proc = None
    procs = []
    try:
        for cmd in cmds:
            proc = subprocess.Popen(shlex.split(cmd), stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if last_proc:
                # Ensure last_proc receives SIGPIPE if proc exits first
                last_proc.stdout.close()
            procs.append(proc)
            stdin = proc.stdout
            last_proc = proc
    finally:
        signal.signal(signal.SIGPIPE, sigpipe_handler)

    last_stderr = last_proc.communicate()[1]

    results = []
    for (cmd, proc) in zip(cmds[:-1], procs[:-1]):
        # wait() is OK here, despite use of PIPE above; these procs
        # are finished.
        proc.wait()
        results.append((proc.returncode, proc.stderr.read()))
    results.append((last_proc.returncode, last_stderr))
    return results

def locate(root, match_function, ignore_dotfiles=True):
    '''
    Yields all filenames within the root directory for which match_function return True.
    '''
    for path, dirs, files in os.walk(root):
        for filename in (os.path.abspath(os.path.join(path, filename)) for filename in files if match_function(filename)):
            if ignore_dotfiles and os.path.basename(filename).startswith('.'):
                pass
            else:
                yield filename

def ext_matcher(*extensions):
    '''
    Returns a function which checks if a filename has one of the specified extensions.
    '''
    return lambda f: os.path.splitext(f)[-1].lower() in extensions

def is_24bit(flac_dir):
    '''
    Returns True if any FLAC within flac_dir is 24 bit.
    '''
    flacs = (mutagen.flac.FLAC(flac_file) for flac_file in locate(flac_dir, ext_matcher('.flac')))
    return any(flac.info.bits_per_sample > 16 for flac in flacs)

# Pool.map() can't pickle lambdas, so we need a helper function.
def pool_transcode((flac_file, output_dir, output_format)):
    return transcode(flac_file, output_dir, output_format)

def transcode(flac_file, output_dir, output_format):
    '''
    Transcodes a FLAC file into another format.
    '''
    # gather metadata from the flac file
    flac_info = mutagen.flac.FLAC(flac_file)
    sample_rate = flac_info.info.sample_rate
    bits_per_sample = flac_info.info.bits_per_sample
    channels = flac_info.info.channels
    dither = sample_rate > 48000 or bits_per_sample > 16

    # determine the new filename
    transcode_file = os.path.join(output_dir, os.path.splitext(os.path.basename(flac_file))[0])
    if not os.path.exists(os.path.dirname(transcode_file)):
        os.makedirs(os.path.dirname(transcode_file))

    # determine the correct transcoding process
    flac_decoder = 'flac -dcs -- %(FLAC)s'

    lame_encoder = 'lame -S %(OPTS)s - %(FILE)s'
    flac_encoder = 'flac %(OPTS)s -o %(FILE)s -'

    downmix_command = 'sox -t wav - -c 2 -t wav -'
    dither_command = 'sox -t wav - -b 16 -r 44100 -t wav -'

    transcoding_steps = [flac_decoder]

    if channels > 2:
        transcoding_steps.append(downmix_command)

    if dither:
        transcoding_steps.append(dither_command)

    if encoders[output_format]['enc'] == 'lame':
        transcoding_steps.append(lame_encoder)
        transcode_file += ".mp3"
    elif encoders[output_format]['enc'] == 'flac':
        transcoding_steps.append(flac_encoder)
        transcode_file += ".flac"

    transcode_args = {
        'FLAC' : pipes.quote(flac_file.encode(sys.getfilesystemencoding())),
        'FILE' : pipes.quote(transcode_file.encode(sys.getfilesystemencoding())),
        'OPTS' : encoders[output_format]['opts']
    }

    if output_format == 'FLAC' and dither:
        transcode_commands = ['sox %(FLAC)s -r 44100 -b 16 %(FILE)s' % transcode_args]
    else:
        transcode_commands = map(lambda cmd : cmd % transcode_args, transcoding_steps)

    results = run_pipeline(transcode_commands)

    # Check for problems. Because it's a pipeline, the earliest one is
    # usually the source. The exception is -SIGPIPE, which is caused
    # by "backpressure" due to a later command failing: ignore those
    # unless no other problem is found.
    last_sigpipe = None
    for (cmd, (code, stderr)) in zip(transcode_commands, results):
        if code:
            if code == -signal.SIGPIPE:
                last_sigpipe = (cmd, (code, stderr))
            else:
                raise TranscodeException('Transcode of file "%s" failed: %s' % (flac_file, stderr))
    if last_sigpipe:
        # XXX: this should probably never happen....
        raise TranscodeException('Transcode of file "%s" failed: SIGPIPE' % flac_file)

    tagging.copy_tags(flac_file, transcode_file)
    (ok, msg) = tagging.check_tags(transcode_file)
    if not ok:
        raise TranscodeException('Tag check failed on transcoded file: %s' % msg)

    return transcode_file

def get_transcode_dir(flac_dir, output_dir, output_format, dither):
    transcode_dir = os.path.basename(flac_dir)

    if 'FLAC' in flac_dir.upper():
        transcode_dir = re.sub(re.compile('FLAC', re.I), output_format, transcode_dir)
    else:
        transcode_dir = transcode_dir + " (" + output_format + ")"
        if output_format != 'FLAC':
            transcode_dir = re.sub(re.compile('FLAC', re.I), '', transcode_dir)
    if dither:
        if '24' in flac_dir and '96' in flac_dir:
            # XXX: theoretically, this could replace part of the album title too.
            # e.g. "24 days in 96 castles - [24-96]" would become "16 days in 44 castles - [16-44]"
            transcode_dir = transcode_dir.replace('24', '16')
            transcode_dir = transcode_dir.replace('96', '44')
        else:
            transcode_dir += " [16-44]"

    return os.path.join(output_dir, transcode_dir)

def transcode_release(flac_dir, output_dir, output_format, max_threads=None):
    '''
    Transcode a FLAC release into another format.
    '''
    flac_dir = os.path.abspath(flac_dir)
    output_dir = os.path.abspath(output_dir)
    flac_files = locate(flac_dir, ext_matcher('.flac'))

    # check if we need to dither to 16/44
    dither = is_24bit(flac_dir)

    # check if we need to encode
    if output_format == 'FLAC' and not dither:
        # XXX: if output_dir is not the same as flac_dir, this may not
        # do what the user expects.
        if output_dir != os.path.dirname(flac_dir):
            print "Warning: no encode necessary, so files won't be placed in", output_dir
        return flac_dir

    # make a new directory for the transcoded files
    #
    # NB: The cleanup code that follows this block assumes that
    # transcode_dir is a new directory created exclusively for this
    # transcode. Do not change this assumption without considering the
    # consequences!
    transcode_dir = get_transcode_dir(flac_dir, output_dir, output_format, dither)
    if not os.path.exists(transcode_dir):
        os.makedirs(transcode_dir)
    else:
        raise TranscodeException('transcode output directory "%s" already exists' % transcode_dir)

    # To ensure that a terminated pool subprocess terminates its
    # children, we make each pool subprocess a process group leader,
    # and handle SIGTERM by killing the process group. This will
    # ensure there are no lingering processes when a transcode fails
    # or is interrupted.
    def pool_initializer():
        os.setsid()
        def sigterm_handler(signum, frame):
            # We're about to SIGTERM the group, including us; ignore
            # it so we can finish this handler.
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            pgid = os.getpgid(0)
            os.killpg(pgid, signal.SIGTERM)
            sys.exit(-signal.SIGTERM)
        signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        # create transcoding threads
        #
        # Use Pool.map() rather than Pool.apply_async() as it will raise
        # exceptions synchronously. (Don't want to waste any more time
        # when a transcode breaks.)
        #
        # XXX: actually, use Pool.map_async() and then get() the result
        # with a large timeout, as a workaround for a KeyboardInterrupt in
        # Pool.join(). c.f.,
        # http://stackoverflow.com/questions/1408356/keyboard-interrupts-with-pythons-multiprocessing-pool?rq=1
        pool = multiprocessing.Pool(max_threads, initializer=pool_initializer)
        try:
            result = pool.map_async(pool_transcode, [(filename, os.path.dirname(filename).replace(flac_dir, transcode_dir), output_format) for filename in flac_files])
            result.get(60 * 60 * 12)
            pool.close()
        except:
            pool.terminate()
            raise
        finally:
            pool.join()

        # copy other files
        allowed_extensions = ['.cue', '.gif', '.jpeg', '.jpg', '.log', '.md5', '.nfo', '.pdf', '.png', '.sfv', '.txt']
        allowed_files = locate(flac_dir, ext_matcher(*allowed_extensions))
        for filename in allowed_files:
            new_dir = os.path.dirname(filename).replace(flac_dir, transcode_dir)
            if not os.path.exists(new_dir):
                os.makedirs(new_dir)
            shutil.copy(filename, new_dir)

        return transcode_dir

    except:
        # Cleanup.
        #
        # ASSERT: transcode_dir was created by this function and does
        # not contain anything other than the transcoded files!
        shutil.rmtree(transcode_dir)
        raise

def make_torrent(input_dir, output_dir, tracker, passkey):
    torrent = os.path.join(output_dir, os.path.basename(input_dir).encode(sys.getfilesystemencoding())) + ".torrent"
    if not os.path.exists(os.path.dirname(torrent)):
        os.path.makedirs(os.path.dirname(torrent))
    tracker_url = '%(tracker)s%(passkey)s/announce' % {
        'tracker' : tracker,
        'passkey' : passkey,
    }
    command = ["mktorrent", "-p", "-a", tracker_url, "-o", torrent, input_dir.encode(sys.getfilesystemencoding())]
    subprocess.check_output(command, stderr=subprocess.STDOUT)
    return torrent

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('input_dir')
    parser.add_argument('output_dir')
    parser.add_argument('output_format', choices=encoders.keys())
    parser.add_argument('-j', '--threads', default=multiprocessing.cpu_count())
    args = parser.parse_args()

    transcode_release(os.path.expanduser(args.input_dir), os.path.expanduser(args.output_dir), args.output_format, args.threads)

if __name__ == "__main__": main()
