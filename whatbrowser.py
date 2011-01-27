#!/usr/bin/env python
import os
import re
import json
import urlparse
import tempfile
import lxml.html
import mechanize
import lxml.html.soupparser
from collections import OrderedDict

import transcode

encoders = OrderedDict((
    ('V0', {
        'format' : 'MP3',
        'bitrate' : 'V0 (VBR)'
        }),
    ('320', {
        'format' : 'MP3',
        'bitrate' : '320'
        }),
    ('V2', {
        'format' : 'MP3', 
        'bitrate' : 'V2 (VBR)'
        }),
    ('Q8', {
        'format' : 'Ogg Vorbis',
        'bitrate' : 'q8.x (VBR)'
        }),
    ('AAC', {
        'format' : 'AAC',
        'bitrate': '320'
        }),
    ('FLAC', {
        'format': 'FLAC',
        'bitrate': 'Lossless'
        })
))

class WhatBrowser(mechanize.Browser):
    def __init__(self, username, password, **kwargs):
        mechanize.Browser.__init__(self)

        self.tracker = "http://tracker.what.cd:34000/"
        for kwarg, value in kwargs.items():
            setattr(self, kwarg, value)

        self.set_handle_robots(False)
        self.open('http://what.cd/login.php')

        self.select_form(nr=0)
        self['username'] = username
        self['password'] = password
        self.submit()

        doc = parse_html(self._response.read())
        self.userid = re.search('[0-9]+$', \
                doc.cssselect('div#userinfo ul#userinfo_username li '
                    + 'a.username')[0].get('href')).group(0)

    def _parse_release_list(self, url, skip=None, params=None):
        if params:
            url += '&' + '&'.join('%s=%s' % (param, value) for param, value in params.iteritems())
        response = self.goto(url)
        done = False
        while not done:
            response = self.goto(url).read()
            doc = parse_html(response)
            for release_url in doc.cssselect('.thin a'):
                if release_url.get('title') == 'View Torrent':
                    url = release_url.get('href')
                    if skip is not None:
                        query_string = urlparse.urlparse(url).query
                        releaseid = urlparse.parse_qs(query_string)['id'][0]
                        if releaseid in skip:
                            continue
                    yield self.get_release(url)
            try:
                #snatched_url = [a.get('href') for a in doc.cssselect('.pager_next')][0]
                url = list(doc.cssselect('.pager_next'))[0].get('href')
            except IndexError:
                done = True
 
    def goto(self, url, refresh=False):
        if self.geturl() != url or refresh:
            return self.open(url)
        else:
            return self._response

    def get_release(self, release_url_or_id):
        if '?' in release_url_or_id:
            # it's a url; extract the useful part
            query_string = urlparse.urlparse(release_url_or_id).query
            params = urlparse.parse_qs(query_string)
            releaseid = params['id'][0]
            if params.has_key('torrentid'):
                torrentid = params['torrentid'][0]
                return Release(self, releaseid, torrentid)
                
        else:
            releaseid = re.search('[0-9]+$', release_url_or_id).group(0)
        return Release(self, releaseid)

    def get_torrent(self, torrent_url_or_id):
        torrentid = re.search('[0-9]+$', torrent_url_or_id).group(0)
        return Torrent(self, torrentid)

    def transcode_candidates(self, skip=None):
        return self._parse_release_list('http://what.cd/better.php?method=snatch', skip)
    
    def snatched(self, skip=None, **params):
        return self._parse_release_list('http://what.cd/torrents.php?type=snatched&userid=%s' % self.userid, skip, params)

class Release:
    def __init__(self, browser, releaseid, torrentid=None):
        self.browser = browser
        self.id = releaseid
        self.torrentid = torrentid
        self.url = 'http://what.cd/torrents.php?id=%s' % self.id
        self.upload_url = 'http://what.cd/upload.php?groupid=%s' % self.id
        self.retrieve_info()
        self.torrents = self.get_torrents()
        if self.torrentid is not None:
            self.torrent = [t for t in self.torrents if t.id == torrentid][0]
        else:
            try:
                self.torrent = [t for t in self.torrents if t.codec == 'FLAC'][0]
            except IndexError:
                self.torrents = list(self.torrents)[0]
        self.media = self.torrent.media
        folder = self.torrent.folder
        if folder.startswith('/'):
            folder = folder[1:]
        self.flac_dir = os.path.join(self.browser.data_dir, folder)

    def retrieve_info(self):
        response = self.browser.goto(self.url).read()
        doc = parse_html(response)
        for header in doc.cssselect('div#content div.thin h2'):
            artist, info = header.text_content().split(' - ', 1)
            self.artist = artist
            result = re.search('([^\[]+)\s\[([^\]]+)\]\s\[([^\]]+)\]', info)
            self.title = result.group(1)
            self.year = result.group(2)
            self.release_type = result.group(3)

        response = self.browser.goto(self.upload_url).read()
        doc = parse_html(response)
        self.editions = []
        for json_editions in doc.cssselect('#json_remasters'):
            # get unique releases
            editions = json.loads(json_editions.get('value'))
            seen = set()
            for edition in editions:
                edition_info = {
                    'title' : edition['RemasterTitle'],
                    'catalog_number' : edition['RemasterCatalogueNumber'],
                    'record_label' : edition['RemasterRecordLabel'],
                    'year' : edition['RemasterYear']
                }
                identifier = ''.join(''.join((k,v)) for k,v in edition_info.iteritems())
                if identifier not in seen:
                    self.editions.append(edition_info)
                    seen.add(identifier)

        try:
            self.album_info = doc.cssselect('html body#torrents div#wrapper div#content div.thin div.main_column div.box div.body')[0].text_content()
        except IndexError:
            self.album_info = None

    def get_torrents(self):
        torrents = []

        response = self.browser.goto(self.url)
        doc = parse_html(response.read())

        for torrent_group in doc.cssselect('.group_torrent'):
            try:
                torrentid = torrent_group.get('id').replace('torrent', '')
                torrents.append(Torrent(self.browser, torrentid))
            except Exception as e:
                continue
        
        return torrents

    def formats_needed(self):
        current_formats = [t.codec for t in self.get_torrents()]
        formats_needed = [codec for codec in encoders.keys() if codec not in current_formats]
        return formats_needed

    def add_format(self, codec):
        transcode_dir = transcode.transcode(self.flac_dir, codec, output_dir=self.browser.data_dir)
        torrent = transcode.make_torrent(transcode_dir, self.browser.torrent_dir, self.browser.tracker, self.browser.passkey)

        self.browser.goto(self.upload_url)
        # select the last form on the page
        self.browser.select_form(nr=len(list(self.browser.forms()))-1) 

        # add the torrent
        self.browser.find_control('file_input').add_file(open(torrent), 'text/plain', os.path.basename(torrent))

        # specify edition information
        if len(self.editions) > 0:
            if len(self.editions) > 1:
                #TODO select edition
                raise NotImplementedError('Releases with more than one edition are currently unsupported.')
            try:
                edition = self.torrent.edition
            except:
                edition = self.editions[0]
            self.browser.find_control('remaster').set_single('1')
    
            if edition['year']:
                self.browser['remaster_year'] = edition['year']
            if edition['title']:
                self.browser['remaster_title'] = edition['title']
            if edition['catalog_number']:
                self.browser['remaster_catalogue_number'] = edition['catalog_number']
            if edition['record_label']:
                self.browser['remaster_record_label'] = edition['record_label']

        # specify format
        self.browser.find_control('format').set('1', encoders[codec]['format'])

        # specify bitrate
        self.browser.find_control('bitrate').set('1', encoders[codec]['bitrate'])

        # specify media
        self.browser.find_control('media').set('1', self.media)

        # specify release description
        self.browser['release_desc'] = 'Created with [url=http://github.com/zacharydenton/whatbetter/]whatbetter[/url].'

        # submit the form
        response = self.browser.submit()
        return response

class Torrent:
    def __init__(self, browser, torrentid):
        self.browser = browser
        self.id = torrentid
        self.url = 'http://what.cd/torrents.php?torrentid=%s' % self.id
        self.folder = None
        self.retrieve_info()

    def retrieve_info(self):
        response = self.browser.goto(self.url).read()
        doc = parse_html(response)
        for torrent_group in doc.cssselect('tr#torrent%s' % self.id):
            for torrent_info in torrent_group.cssselect('td a'):
                if torrent_info.text_content() in ['RP', 'ED', 'RM', 'PL']:
                    continue
                elif torrent_info.text_content() == 'DL':
                    self.download_link = torrent_info.get('href')
                else:
                    info = torrent_info.text_content()[1:].strip() # trim leading char
                    result = info.split(' / ')
                    if 'Reported' in result:
                        result.pop()
                    self.format = result[0].strip()
                    self.bitrate = result[1].strip()
                    self.media = result[-1].strip()
                    self.codec = get_codec(self.format, self.bitrate)
                    try:
                        scene = result[3]
                        self.scene = True
                    except IndexError:
                        self.scene = False

        for filelist in doc.cssselect('#files_%s' % self.id):
            self.files = []
            for i, row in enumerate(filelist.cssselect('tr')):
                if i == 0:
                    for heading in row.cssselect('td div'):
                        if heading.text_content().startswith('/'):
                            self.folder = heading.text_content().strip()
                            break
                    continue
                self.files.append(row.cssselect('td')[0].text_content())
        if not self.folder and len(self.files) == 1:
            self.folder = self.files[0]
            print(self.folder)
                
    def download(self, output_dir=None):
        if output_dir is None:
            output_dir = self.browser.torrent_dir
        path = os.path.join(output_dir, self.get_filename())
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
