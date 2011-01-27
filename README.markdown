whatbetter
==========

Introduction
------------
whatbetter is a script which automatically transcodes and uploads FLACs on What.CD.

The following command will scan through every FLAC you have ever downloaded, determine which formats are needed, transcode the FLAC to each needed format, and upload each format to What.CD -- no user input required.

    $ whatbetter --all

Installation
------------
As an artifact of power, whatbetter requires that its would-be wielders pass a series of tests before use. This is all in the spirit of What.CD, of course.

First of all, you're going to need Python to run whatbetter. Python 3 is unsupported due to the dependency on mechanize, which does not currently support Python 3.

Once you've got Python installed, you need several modules: mechanize, mutagen, lxml, and BeautifulSoup. Try this:

    # pip install mechanize mutagen lxml BeautifulSoup

Furthermore, you need several external programs: mktorrent, flac, lame, oggenc, ffmpeg, and neroAacEnc. The method of installing these programs varies depending on your operating system, but if you're using something like Ubuntu you can do this:

    # aptitude install mktorrent flac lame vorbis-tools ffmpeg

For neroAacEnc, you need to download the encoder from [nero](http://www.nero.com/eng/downloads-nerodigital-nero-aac-codec.php), extract it, and place the binaries somewhere on your PATH.

At this point you may begin to speak with whatbetter. Perform the following command:

    $ whatbetter

And you will receive a notification stating that you should edit the configuration file ~/.whatbetter/config (if you're lucky).

Configuration
-------------
You've made it far! Congratulations. Open up the file ~/.whatbetter/config in a text editor. You're going to see something like this:

    [whatcd]
    username =
    password = 
    passkey = 
    data_dir =
    torrent_dir =

The username and password are your What.CD login credentials. The passkey is your tracker passkey. The data_dir is the directory where your downloads are stored. The torrent_dir is the directory where torrents should be created (e.g., your watch directory).

You should end up with something like this:

    [whatcd]
    username = RequestBunny
    password = clapton
    passkey = as309uasdfklwwe90sakjlsd
    data_dir = ~/Downloads
    torrent_dir = ~/Torrents

Alright! Now you're ready to use whatbetter.

Usage
-----
    usage: whatbetter [-h] [-A] [-a] [--config CONFIG] [--cache CACHE]
                    [release_urls [release_urls ...]]
    
    positional arguments:
    release_urls     the URL where the release is located
    
    optional arguments:
    -h, --help       show this help message and exit
    -A, --auto       attempt to automatically find transcode candidates
    -a, --all        search through all snatched torrents for transcode
                    candidates
    --config CONFIG  the location of the configuration file (default:
                    ~/.whatbetter/config)
    --cache CACHE    the location of the cache (default: ~/.whatbetter/cache)
    
Examples
--------
To transcode and upload releases that are listed in the 'Snatch' section of better.php:

    $ whatbetter --auto

To expand the search to every FLAC you've ever downloaded (this may take a while):

    $ whatbetter --all

To transcode and upload a specific release (provided you have already downloaded the FLAC and it is located in your data_dir):

    $ whatbetter http://what.cd/torrents.php?id=1000&torrentid=1000000
