#!/usr/bin/env python
import os
import re
import sys
import pipes
import shutil
import fnmatch
import subprocess
import multiprocessing
import mediafile

encoders = {
    '320':  {'enc': 'lame',     'opts': '-b 320 --ignore-tag-errors'},
    'V0':   {'enc': 'lame',     'opts': '-V 0 --vbr-new --ignore-tag-errors'},
    'V2':   {'enc': 'lame',     'opts': '-V 2 --vbr-new --ignore-tag-errors'},
    'Q8':   {'enc': 'oggenc',   'opts': '-q 8'},
    'AAC':  {'enc': 'neroAacEnc',   'opts': '-br 320000'},
    'ALAC': {'enc': 'ffmpeg',   'opts': '-i - -acodec alac'},
    'FLAC': {'enc': 'flac',     'opts': '--best'}
}

def locate(root, match_function):
    '''
    Yields all filenames within the root directory for which match_function return True.
    '''
    for path, dirs, files in os.walk(root):
        for filename in (os.path.abspath(os.path.join(path, filename)) for filename in files if match_function(filename)):
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
    flacs = (mediafile.MediaFile(flac_file) for flac_file in locate(flac_dir, ext_matcher('.flac')))
    return any(flac.mgfile.info.bits_per_sample > 16 for flac in flacs)

def transcode(flac_file, output_dir, output_format):
    '''
    Transcodes a FLAC file into another format.
    '''
    # gather metadata from the flac file
    flac_info = mediafile.MediaFile(flac_file)
    sample_rate = flac_info.mgfile.info.sample_rate
    bits_per_sample = flac_info.mgfile.info.bits_per_sample
    dither = sample_rate > 48000 or bits_per_sample > 16

    # determine the new filename
    transcode_file = os.path.join(output_dir, os.path.splitext(os.path.basename(flac_file))[0])
    if not os.path.exists(os.path.dirname(transcode_file)):
        os.makedirs(os.path.dirname(transcode_file))

    # determine the correct transcoding process
    flac_decoder = 'flac -dcs -- %(FLAC)s'

    lame_encoder = 'lame -S %(OPTS)s - %(FILE)s'
    ogg_encoder = 'oggenc -Q %(OPTS)s -o %(FILE)s -'
    ffmpeg_encoder = 'ffmpeg %(OPTS)s %(FILE)s'
    nero_encoder = 'neroAacEnc %(OPTS)s -if - -of %(FILE)s'
    flac_encoder = 'flac %(OPTS)s -o %(FILE)s -'

    dither_command = 'sox -t wav - -b 16 -r 44100 -t wav -'

    transcoding_steps = [flac_decoder]

    if dither:
        transcoding_steps.append(dither_command)

    if encoders[output_format]['enc'] == 'lame':
        transcoding_steps.append(lame_encoder)
        transcode_file += ".mp3"
    elif encoders[output_format]['enc'] == 'oggenc':
        transcoding_steps.append(ogg_encoder)
        transcode_file += ".ogg"
    elif encoders[output_format]['enc'] == 'ffmpeg':
        transcoding_steps.append(ffmpeg_encoder)
        transcode_file += ".alac"
    elif encoders[output_format]['enc'] == 'neroAacEnc':
        transcoding_steps.append(nero_encoder)
        transcode_file += ".m4a"
    elif encoders[output_format]['enc'] == 'flac':
        transcoding_steps.append(flac_encoder)
        transcode_file += ".flac"

    transcode_args = {
        'FLAC' : pipes.quote(flac_file.encode(sys.getfilesystemencoding())),
        'FILE' : pipes.quote(transcode_file.encode(sys.getfilesystemencoding())),
        'OPTS' : encoders[output_format]['opts']
    }

    transcode_command = ' | '.join(transcoding_steps) % transcode_args

    if output_format == 'FLAC' and dither:
        # for some reason, FLAC | SoX | FLAC does not work.
        # use files instead.
        transcode_args['TEMP'] = tempfile.mkstemp('.wav')
        transcode_command = ''.join([flac_decoder, ' | ', dither_command, ' > %(TEMP)s; ', \
                flac_encoder, ' < %(TEMP)s; rm %(TEMP)s']) % transcode_args
        
    subprocess.check_output(transcode_command, shell=True, stderr=subprocess.STDOUT)

    # tag the file
    transcode_info = mediafile.MediaFile(transcode_file)
    skip = ['format', 'type', 'bitrate', 'mgfile', 'save']
    for attribute in dir(flac_info):
        if not attribute.startswith('_') and attribute not in skip:
            try:
                setattr(transcode_info, attribute, getattr(flac_info, attribute))
            except:
                continue

    transcode_info.save()

    return transcode_file

def get_transcode_dir(flac_dir, output_format, dither):
    transcode_dir = flac_dir

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

    return transcode_dir

def transcode_release(flac_dir, output_format, max_threads=None):
    '''
    Transcode a FLAC release into another format.
    '''
    flac_dir = os.path.abspath(flac_dir)
    flac_files = locate(flac_dir, ext_matcher('.flac'))

    # check if we need to dither to 16/44
    dither = is_24bit(flac_dir)

    # check if we need to encode
    if output_format == 'FLAC' and not dither:
        return flac_dir

    # make a new directory for the transcoded files
    transcode_dir = get_transcode_dir(flac_dir, output_format, dither)
    if not os.path.exists(transcode_dir):
        os.makedirs(transcode_dir)

    # create transcoding threads
    pool = multiprocessing.Pool(max_threads)
    for filename in flac_files:
        pool.apply_async(transcode, (filename, os.path.dirname(filename).replace(flac_dir, transcode_dir), output_format))

    pool.close()
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
