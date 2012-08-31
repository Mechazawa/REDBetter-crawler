#!/usr/bin/env python
import re
import os
import json
import requests
import mechanize
import htmlentitydefs
from cStringIO import StringIO

headers = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3)'\
        'AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.79'\
        'Safari/535.11',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9'\
        ',*/*;q=0.8',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'en-US,en;q=0.8',
    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3'}

formats = {
    'FLAC': {
        'format': 'FLAC',
        'encoding': 'Lossless'
    },
    'V0': {
        'format' : 'MP3',
        'encoding' : 'V0 (VBR)'
    },
    '320': {
        'format' : 'MP3',
        'encoding' : '320'
    },
    'V2': {
        'format' : 'MP3', 
        'encoding' : 'V2 (VBR)'
    },
    'AAC': {
        'format' : 'AAC',
        'encoding': '320'
    },
}

class LoginException(Exception):
    pass

class RequestException(Exception):
    pass

class WhatAPI:
    def __init__(self, username=None, password=None):
        self.session = requests.session(headers=headers)
        self.username = username
        self.password = password
        self.authkey = None
        self.passkey = None
        self.userid = None
        self.tracker = "http://tracker.what.cd:34000/"
        self._login()

    def _login(self):
        '''Logs in user and gets authkey from server'''
        loginpage = 'https://what.cd/login.php'
        data = {'username': self.username,
                'password': self.password}
        r = self.session.post(loginpage, data=data)
        if r.status_code != 200:
            raise LoginException
        accountinfo = self.request('index')
        self.authkey = accountinfo['authkey']
        self.passkey = accountinfo['passkey']
        self.userid = accountinfo['id']

    def request(self, action, **kwargs):
        '''Makes an AJAX request at a given action page'''
        ajaxpage = 'https://what.cd/ajax.php'
        params = {'action': action}
        if self.authkey:
            params['auth'] = self.authkey
        params.update(kwargs)
        r = self.session.get(ajaxpage, params=params, allow_redirects=False)
        try:
            parsed = json.loads(r.content)
            if parsed['status'] != 'success':
                raise RequestException
            return parsed['response']
        except ValueError:
            raise RequestException
    
    def get_artist(self, id=None, format='MP3', best_seeded=True):
        res = self.request('artist', id=id)
        torrentgroups = res['torrentgroup']
        keep_releases = []
        for release in torrentgroups:
            torrents = release['torrent']
            best_torrent = torrents[0]
            keeptorrents = []
            for t in torrents:
                if t['format'] == format:
                    if best_seeded:
                        if t['seeders'] > best_torrent['seeders']:
                            keeptorrents = [t]
                            best_torrent = t
                    else:
                        keeptorrents.append(t)
            release['torrent'] = list(keeptorrents)
            if len(release['torrent']):
                keep_releases.append(release)
        res['torrentgroup'] = keep_releases
        return res

    def snatched(self, skip=None):
        page = 1
        done = False
        url = 'https://what.cd/torrents.php?type=snatched&userid=%s&format=FLAC' % self.userid
        while not done:
            content = self.session.get(url + "&page=%s" % page).text
            pattern = re.compile('torrents.php\?id=(\d+)&amp;torrentid=(\d+)')
            for groupid, torrentid in pattern.findall(content):
                if not skip or torrentid not in skip:
                    yield int(groupid), int(torrentid)
            done = 'Next &gt;' not in content
            page += 1

    def upload(self, group, torrent, new_torrent, format):
        url = "https://what.cd/upload.php?groupid=%s" % group['group']['id']
        response = self.session.get(url)
        forms = mechanize.ParseFile(StringIO(response.text), url)
        form = forms[-1]
        form.find_control('file_input').add_file(open(new_torrent), 'application/x-bittorrent', os.path.basename(new_torrent))
        if torrent['remastered']:
            form.find_control('remaster').set_single('1')
            form['remaster_year'] = str(torrent['remasterYear'])
            form['remaster_title'] = torrent['remasterTitle']
            form['remaster_record_label'] = torrent['remasterRecordLabel']
            form['remaster_catalogue_number'] = torrent['remasterCatalogueNumber']

        form.find_control('format').set('1', formats[format]['format'])
        form.find_control('bitrate').set('1', formats[format]['encoding'])
        form.find_control('media').set('1', torrent['media'])
        form['release_desc'] = 'Created with [url=http://github.com/zacharydenton/whatbetter]whatbetter[/url].'
        _, data, headers = form.click_request_data()
        response = self.session.post(url, data=data, headers=dict(headers))

def unescape(text):
   """Removes HTML or XML character references 
      and entities from a text string.
      keep &amp;, &gt;, &lt; in the source code.
   from Fredrik Lundh
   http://effbot.org/zone/re-sub.htm#unescape-html
   """
   def fixup(m):
      text = m.group(0)
      if text[:2] == "&#":
         # character reference
         try:
            if text[:3] == "&#x":
               return unichr(int(text[3:-1], 16))
            else:
               return unichr(int(text[2:-1]))
         except ValueError:
            pass
      else:
         # named entity
         try:
            if text[1:-1] == "amp":
               text = "&amp;amp;"
            elif text[1:-1] == "gt":
               text = "&amp;gt;"
            elif text[1:-1] == "lt":
               text = "&amp;lt;"
            else:
               text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
         except KeyError:
            pass
      return text # leave as is
   return re.sub("&#?\w+;", fixup, text)
