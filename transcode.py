#!/usr/bin/env python
import os
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
        transcode_args = {
            'FLAC' : self.flac_file,
            'FILE' : transcode_file,
            'OPTS' : encoders[codec]['opts']
        }

        flac_decoder = 'flac -dc -- %(FLAC)s'

        lame_encoder = 'lame -S %(OPTS)s - %(FILE)s.mp3'
        ogg_encoder = 'oggenc -Q %(OPTS)s -o %(FILE)s.ogg -'
        ffmpeg_encoder = 'ffmpeg %(OPTS)s %(FILE)s.m4a'
        nero_encoder = 'neroAacEnc %(OPTS)s -if - -of %(FILE)s.m4a'
        flac_encoder = 'flac %(OPTS)s -o %(FILE)s.flac -'

        dither_command = 'sox -t wav - -b 16 -r 44100 -t wav -'

        transcoding_steps = [flac_decoder]

        if self.dither:
            transcoding_steps.append(dither_command)

        if encoders[self.codec]['enc'] == 'lame':
            transcoding_steps.append(lame_encoder)
        elif encoders[self.codec]['enc'] == 'oggenc':
            transcoding_steps.append(ogg_encoder)
        elif encoders[self.codec]['enc'] == 'ffmpeg':
            transcoding_steps.append(ffmpeg_encoder)
        elif encoders[self.codec]['enc'] == 'neroAacEnc':
            transcoding_steps.append(nero_encoder)
        elif encoders[self.codec]['enc'] == 'flac':
            transcoding_steps.append(flac_encoder)

        transcode_command = ' | '.join(transcoding_steps) % transcode_args
        
        # transcode the file
        os.system(escape(transcode_command))

        # tag the file
        transcode_info = mediafile.MediaFile(transcode_file)
        transcode_info.mgfile.tags = flac_info.mgfile.tags
        transcode_info.save()

        self.cv.acquire()
        self.cv.notify_all()
        self.cv.release()

        return 0

def transcode(flac_dir, codec, max_threads=cpu_count()):
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
    transcode_dir = get_directory_name(flac_dir, codec)
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
