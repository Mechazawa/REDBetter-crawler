#!/usr/bin/env python
import os
import re
import tempfile
import lxml.html
import lxml.html.soupparser
import mechanize

encoders = {
    '320': {
        'format' : 'MP3',
        'bitrate' : '320'
        },
    'V0': {
        'format' : 'MP3',
        'bitrate' : 'V0 (VBR)'
        },
    'V2': {
        'format' : 'MP3', 
        'bitrate' : 'V2 (VBR)'
        },
    'Q8': {
        'format' : 'Ogg Vorbis',
        'bitrate' : 'q8.x (VBR)'
        },
    'AAC': {
        'format' : 'AAC',
        'bitrate': '320'
        },
    'FLAC': {
        'format': 'FLAC',
        'bitrate': 'Lossless'
        }
}

class WhatBrowser(mechanize.Browser):
    def __init__(self, username, password):
        mechanize.Browser.__init__(self)

        self.set_handle_robots(False)
        self.open('http://what.cd/login.php')

        self.select_form(nr=0)
        self['username'] = username
        self['password'] = password
        self.submit()

    def goto(self, url, refresh=False):
        if self.geturl() != url or refresh:
            return self.open(url)
        else:
            return self._response

    def get_release(self, release_url_or_id):
        releaseid = re.search('[0-9]+$', release_url_or_id).group(0)
        return Release(self, releaseid)

    def get_torrent(self, torrent_url_or_id):
        torrentid = re.search('[0-9]+$', torrent_url_or_id).group(0)
        return Torrent(self, torrentid)

    def transcode_candidates(self):
        self.goto('http://what.cd/better.php?method=snatch')
        doc = parse_html(self._response.read())

        for release_url in doc.cssselect('.thin a'):
            if release_url.get('title') == 'View Torrent':
                url = release_url.get('href')
                yield self.get_release(url)

class Release:
    def __init__(self, browser, releaseid):
        self.browser = browser
        self.id = releaseid
        self.url = 'http://what.cd/torrents.php?id=%s' % self.id
        self.get_release_info()
        self.torrents = self.get_torrents()

    def get_release_info(self):
        response = self.browser.goto(self.url).read()
        doc = parse_html(response)
        for header in doc.cssselect('div#content div.thin h2'):
            artist, info = header.text_content().split(' - ')
            self.artist = artist
            result = re.search('([^\[]+)\s\[([^\]]+)\]\s\[([^\]]+)\]', info)
            self.title = result.group(1)
            self.year = result.group(2)
            self.type = result.group(3)

    def get_torrents(self):
        try:
            return self.torrents
        except:
            pass

        torrents = []

        self.browser.goto(self.url)
        doc = parse_html(self.browser._response.read())

        for torrent_group in doc.cssselect('.group_torrent'):
            try:
                torrentid = torrent_group.get('id').replace('torrent', '')
                torrents.append(Torrent(self.browser, torrentid))
            except:
                continue
        
        return torrents

class Torrent:
    def __init__(self, browser, torrentid):
        self.browser = browser
        self.id = torrentid
        self.url = self.get_url()

    def get_url(self):
        pass

    def download(self, output_dir=None):
        if output_dir is None:
            output_dir = os.getcwd()
        path = os.path.join(output_dir, self.filename)
        filename, headers = self.browser.urlretrieve(self.url, path)
        return filename

def parse_html(html):
    try:
        return lxml.html.fromstring(html)
    except:
        return lxml.html.soupparser.fromstring(html)

def get_codec(fmt, bitrate):
    for codec, properties in encoders.items():
        if properties['format'] == fmt and properties['bitrate'] == bitrate:
            return codec
    return None
