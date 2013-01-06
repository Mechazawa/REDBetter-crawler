Introduction
------------

whatbetter is a script which automatically transcodes and uploads FLACs
on What.CD.

The following command will scan through every FLAC you have ever
downloaded, determine which formats are needed, transcode the FLAC to
each needed format, and upload each format to What.CD -- automatically.

    $ whatbetter

Installation
------------

You're going to need to install a few dependencies before using
whatbetter.

First and foremost, you will need Python 2.7 or newer.

Once you've got Python installed, you will need a few modules: mechanize,
mutagen, and requests. Try this:

    $ pip install -r requirements.txt

Alternatively, if you have setuptools installed, you can do this (in the
source directory):

    $ python setup.py install

This should theoretically install all required dependencies
automatically.

Furthermore, you need several external programs: mktorrent, flac, lame,
sox, and neroAacEnc. The method of installing these programs
varies depending on your operating system, but if you're using something
like Ubuntu you can do this:

    # aptitude install mktorrent flac lame sox

For neroAacEnc, you need to download the encoder from
[nero](http://www.nero.com/eng/downloads-nerodigital-nero-aac-codec.php),
extract it, and place the binaries somewhere on your PATH. If you're on
a 64 bit system make sure you have `ia32-libs` installed.

At this point you may execute the following command:

    $ whatbetter

And you will receive a notification stating that you should edit the
configuration file \~/.whatbetter/config (if you're lucky).

Configuration
-------------

You've made it far! Congratulations. Open up the file
\~/.whatbetter/config in a text editor. You're going to see something
like this:

    [whatcd]
    username =
    password = 
    data_dir =
    output_dir =
    torrent_dir =
    formats = flac, v0, 320, v2, aac

`username` and `password` are your What.CD login credentials. 
`data_dir` is the directory where your downloads are stored. 
`output_dir` is the directory where your transcodes will be created. If
the value is blank, `data_dir` will be used.
`torrent_dir` is the directory where torrents should be created (e.g.,
your watch directory). `formats` is a list of formats that you'd like to
support (so if you don't want to upload AAC, just remove it from this
list).

You should end up with something like this:

    [whatcd]
    username = RequestBunny
    password = clapton
    data_dir = /srv/downloads
    output_dir =
    torrent_dir = /srv/torrents
    formats = flac, v0, 320

Alright! Now you're ready to use whatbetter.

Usage
-----

    usage: whatbetter [-h] [-s] [--config CONFIG] [--cache CACHE]
                      [release_urls [release_urls ...]]

    positional arguments:
      release_urls     the URL where the release is located

    optional arguments:
      -h, --help       show this help message and exit
      -s, --single     only add one format per release (useful for getting unique
                       groups)
      --config CONFIG  the location of the configuration file (default:
                       ~/.whatbetter/config)
      --cache CACHE    the location of the cache (default: ~/.whatbetter/cache)

Examples
--------

To transcode and upload every FLAC you've every downloaded (this may
take a while):

    $ whatbetter

To transcode and upload a specific release (provided you have already
downloaded the FLAC and it is located in your `data_dir`):

    $ whatbetter http://what.cd/torrents.php?id=1000&torrentid=1000000
