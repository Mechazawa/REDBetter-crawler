#!/usr/bin/env python
import os
import re
import shlex
import shutil
import fnmatch
import threading
import subprocess
from multiprocessing import cpu_count

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

class Transcode(threading.Thread):
    def __init__(self, flac_file, flac_dir, transcode_dir, codec, dither, cv):
        threading.Thread.__init__(self)
        self.flac_file = flac_file
        self.flac_dir = flac_dir
        self.transcode_dir = transcode_dir
        self.codec = codec
        self.dither = dither
        self.cv = cv

    def run(self):
        # gather metadata from the flac file
        flac_info = mediafile.MediaFile(self.flac_file)

        # determine the new filename
        transcode_file = re.sub(re.escape(self.flac_dir), self.transcode_dir, self.flac_file)
        transcode_file = re.sub('\.flac$', '', transcode_file)

        # make sure the path exists
        if not os.path.exists(os.path.dirname(transcode_file)):
            os.makedirs(os.path.dirname(transcode_file))

        # determine the correct transcoding process
        flac_decoder = 'flac -dcs -- "%(FLAC)s"'

        lame_encoder = 'lame -S %(OPTS)s - "%(FILE)s" > /dev/null 2> /dev/null'
        ogg_encoder = 'oggenc -Q %(OPTS)s -o "%(FILE)s" - > /dev/null 2> /dev/null'
        ffmpeg_encoder = 'ffmpeg %(OPTS)s "%(FILE)s" > /dev/null 2> /dev/null'
        nero_encoder = 'neroAacEnc %(OPTS)s -if - -of "%(FILE)s" > /dev/null 2> /dev/null'
        flac_encoder = 'flac %(OPTS)s -o "%(FILE)s" - > /dev/null 2> /dev/null'

        dither_command = 'sox -t wav - -b 16 -r 44100 --norm -t wav -'

        transcoding_steps = [flac_decoder]

        if self.dither:
            transcoding_steps.append(dither_command)

        if encoders[self.codec]['enc'] == 'lame':
            transcoding_steps.append(lame_encoder)
            transcode_file += ".mp3"
        elif encoders[self.codec]['enc'] == 'oggenc':
            transcoding_steps.append(ogg_encoder)
            transcode_file += ".ogg"
        elif encoders[self.codec]['enc'] == 'ffmpeg':
            transcoding_steps.append(ffmpeg_encoder)
            transcode_file += ".alac"
        elif encoders[self.codec]['enc'] == 'neroAacEnc':
            transcoding_steps.append(nero_encoder)
            transcode_file += ".m4a"
        elif encoders[self.codec]['enc'] == 'flac':
            transcoding_steps.append(flac_encoder)
            transcode_file += ".flac"

        transcode_args = {
            'FLAC' : self.flac_file,
            'FILE' : transcode_file,
            'OPTS' : encoders[self.codec]['opts']
        }

        transcode_command = ' | '.join(transcoding_steps) % transcode_args

        if self.dither and self.codec == 'FLAC':
            # for some reason, FLAC | SoX | FLAC does not work.
            # use files instead.
            transcode_args['TEMP'] = self.flac_file + ".wav"
            transcode_command = ''.join([flac_decoder, ' | ', dither_command, ' > "%(TEMP)s"; ', \
                    flac_encoder, ' < "%(TEMP)s"; rm "%(TEMP)s"']) % transcode_args
        
        # transcode the file
        subprocess.Popen(shlex.split(transcode_command), stdout=subprocess.PIPE,
                stderr=PIPE)

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

        self.cv.acquire()
        self.cv.notify_all()
        self.cv.release()

        return 0

def get_transcode_dir(flac_dir, codec, dither, output_dir=None):
    if output_dir is None:
        transcode_dir = flac_dir
    else:
        transcode_dir = os.path.join(output_dir, os.path.basename(flac_dir))

    if 'FLAC' in flac_dir.upper():
        transcode_dir = re.sub(re.compile('FLAC', re.I), codec, transcode_dir)
    else:
        transcode_dir = transcode_dir + " (" + codec + ")"
        if codec != 'FLAC':
            transcode_dir = re.sub(re.compile('FLAC', re.I), '', transcode_dir)
    if dither:
        if '24' in flac_dir and '96' in flac_dir:
            # XXX: theoretically, this could replace part of the album title too.
            # e.g. "24 days in 96 castles - [24-96]" would become "16 days in 44 castles - [16-44]"
            transcode_dir = re.sub(re.compile('24', re.I), '16', transcode_dir)
            transcode_dir = re.sub(re.compile('96', re.I), '44', transcode_dir)
        else:
            transcode_dir += " [16-44]"

    return transcode_dir

def transcode(flac_dir, codec, max_threads=cpu_count(), output_dir=None):
    '''transcode a directory of FLACs to another format'''
    if codec not in encoders.keys():
        return None
    
    flac_dir = os.path.abspath(flac_dir)
    flac_files = []
    log_files = []
    images = []

    # classify the files
    for path, dirs, files in os.walk(flac_dir, topdown=False):
        for name in files:
            canonical = os.path.join(path, name)
            if fnmatch.fnmatch(name, '*.flac'):
                flac_files.append(canonical)
            elif fnmatch.fnmatch(name, '*.log'):
                log_files.append(canonical)
            elif fnmatch.fnmatch(name, '*.jpg'):
                images.append(canonical)

    # determine sample rate & bits per sample
    flac_info = mediafile.MediaFile(flac_files[0])
    sample_rate = flac_info.mgfile.info.sample_rate
    bits_per_sample = flac_info.mgfile.info.bits_per_sample

    # check if we need to dither to 16/44
    if sample_rate > 44100 or bits_per_sample > 16:
        dither = True
    else:
        dither = False

    # check if we need to encode
    if dither == False and codec == 'FLAC':
        return flac_dir

    # make a new directory for the transcoded files
    transcode_dir = get_transcode_dir(flac_dir, codec, dither, output_dir)
    if not os.path.exists(transcode_dir):
        os.makedirs(transcode_dir)

    # create transcoding threads
    threads = []
    cv = threading.Condition()
    for flac_file in flac_files:
        cv.acquire()
        while threading.active_count() == (max_threads + 1):
            cv.wait()
        cv.release()
        t = Transcode(flac_file, flac_dir, transcode_dir, codec, dither, cv)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    
    # copy other files
    for path, dirs, files in os.walk(flac_dir, topdown=False):
        for name in files:
            if not fnmatch.fnmatch(name, '*.flac') and not fnmatch.fnmatch(name, '*.m3u'):
                d = re.sub(re.escape(flac_dir), transcode_dir, path)
                if not os.path.exists(d):
                    os.makedirs(d)
                shutil.copy(os.path.join(path, name), d)

    return transcode_dir

def make_torrent(input_dir, output_dir, tracker, passkey):
    torrent = os.path.join(output_dir, os.path.basename(input_dir)) + ".torrent"
    if not os.path.exists(os.path.dirname(torrent)):
        os.path.makedirs(os.path.dirname(torrent))
    torrent_command = 'mktorrent -p -a "%(tracker)s%(passkey)s/announce" -o "%(torrent)s" "%(input_dir)s"' % {
        'tracker' : tracker,
        'passkey' : passkey,
        'torrent' : torrent,
        'input_dir' : input_dir
    }
    subprocess.call(torrent_command, shell=True)
    return torrent
