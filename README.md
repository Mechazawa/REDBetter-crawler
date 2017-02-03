Introduction
------------

apollobetter is a script which automatically transcodes and uploads these
files to apollo.rip.

The following command will scan through every FLAC you have ever
downloaded (if it is in , determine which formats are needed, transcode the FLAC to
each needed format, and upload each format to Apollo -- automatically.

    $ apollobetter

Installation
------------

You're going to need to install a few dependencies before using
apollobetter.

First and foremost, you will need Python 2.7 or newer.

Once you've got Python installed, you will need a few modules: mechanize,
mutagen, and requests. Try this:

    $ pip install -r requirements.txt

	
If you are on a seedbox, or a system without root priviliages, try this:


    $ pip install --user -r requirements.txt


Alternatively, if you have setuptools installed, you can do this (in the
source directory):

    $ python setup.py install

This should theoretically install all required dependencies
automatically.

Furthermore, you need several external programs: mktorrent, flac,
lame, and sox. The method of installing these programs varies
depending on your operating system, but if you're using something like
Ubuntu you can do this:

    # aptitude install mktorrent flac lame sox
	

If you are on a seedbox and you lack the privilages to install packages,
you could contact your provider to have these packages installed.

At this point you may execute the following command:

    $ apollobetter

And you will receive a notification stating that you should edit the
configuration file \~/.apollobetter/config (if you're lucky).

Configuration
-------------

You've made it far! Congratulations. Open up the file
\~/.apollobetter/config in a text editor. You're going to see something
like this:

    [whatcd]
    username =
    password = 
    data_dir =
    output_dir =
    torrent_dir =
    formats = flac, v0, 320, v2
    media = sacd, soundboard, web, dvd, cd, dat, vinyl, blu-ray
    24bit_behaviour = 0
    tracker = https://mars.apollo.rip

`username` and `password` are your apollo.rip login credentials. 
`data_dir` is the directory where your downloads are stored. 
`output_dir` is the directory where your transcodes will be created. If
the value is blank, `data_dir` will be used.
`torrent_dir` is the directory where torrents should be created (e.g.,
your watch directory). `formats` is a list of formats that you'd like to
support (so if you don't want to upload V2, just remove it from this
list).
`media` is a list of lossless media types you want to consider for
transcoding. The default value is all What.CD lossless formats, but if
you want to transcode only CD and vinyl media, for example, you would
set this to 'cd, vinyl'.
`24bit_behaviour` defines what happens when the program encounters a FLAC 
that it thinks is 24bits. If it is set to '2', every FLAC that has a bits-
per-sample property of 24 will be silently re-categorized. If it set to '1',
a prompt will appear. The default is '0' which ignores these occurrences.

You should end up with something like this:

    [whatcd]
    username = RequestBunny
    password = clapton
    data_dir = /srv/downloads
    output_dir =
    torrent_dir = /srv/torrents
    formats = flac, v0, 320
    media = cd, vinyl, web
    24bit_behaviour = 0
    tracker = https://mars.apollo.rip

Alright! Now you're ready to use apollobetter.

Usage
-----

    usage: apollobetter [-h] [-s] [--config CONFIG] [--cache CACHE]
                        [release_urls [release_urls ...]]

    positional arguments:
      release_urls     the URL where the release is located, if only one url is
                       specified and is a file it is instead loaded as a list of
                       urls

    optional arguments:
      -h, --help       show this help message and exit
      -s, --single     only add one format per release (useful for getting unique
                       groups)
      --config CONFIG  the location of the configuration file (default:
                       ~/.apollobetter/config)
      --cache CACHE    the location of the cache (default: ~/.apollobetter/cache)

Examples
--------

To transcode and upload every snatch you've ever downloaded (this may
take a while):

    $ apollobetter

To transcode and upload a specific release (provided you have already
downloaded the FLAC and it is located in your `data_dir`):

    $ apollobetter http://apollo.rip/torrents.php?id=1000\&torrentid=1000000

Note that if you specify a particular release(s), apollobetter will
ignore your configuration's media types and attempt to transcode the
releases you have specified regardless of their media type (so long as
they are lossless types).

Your first time running apollobetter might take a while, but after it has
successfully gone through and checked everything, it'll go faster any
consecutive runs due to itss caching method
