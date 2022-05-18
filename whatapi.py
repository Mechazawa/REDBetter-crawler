#!/usr/bin/env python3
import re
import os
import json
import time
import mechanicalsoup
import html

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

# gazelle is picky about case in searches with &media=x
media_search_map = {
    'cd': 'CD',
    'dvd': 'DVD',
    'vinyl': 'Vinyl',
    'soundboard': 'Soundboard',
    'sacd': 'SACD',
    'dat': 'DAT',
    'web': 'WEB',
    'blu-ray': 'Blu-ray'
    }

lossless_media = set(media_search_map.keys())

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
}

def allowed_transcodes(torrent):
    """Some torrent types have transcoding restrictions."""
    preemphasis = re.search(r"""pre[- ]?emphasi(s(ed)?|zed)""", torrent['remasterTitle'], flags=re.IGNORECASE)
    if preemphasis:
        return []
    else:
        return formats.keys()

class LoginException(Exception):
    pass

class RequestException(Exception):
    pass

class WhatAPI:
    def __init__(self, username=None, password=None, endpoint=None, totp=None):
        self.session = mechanicalsoup.StatefulBrowser()
        self.session.session.headers.update(headers)
        self.browser = None
        self.username = username
        self.password = password
        self.totp = totp
        if endpoint:
            self.endpoint = endpoint
        else:
            self.endpoint = 'https://orpheus.network'
        self.authkey = None
        self.passkey = None
        self.userid = None
        self.last_request = time.time()
        self.rate_limit = 2.0 # seconds between requests
        self._login()

    def _login(self):
        '''Logs in user and gets authkey from server'''
        loginpage = '{0}/login.php'.format(self.endpoint)
        data = {'username': self.username,
                'password': self.password}
        r = self.session.post(loginpage, data=data)
        if r.status_code != 200:
            raise LoginException
        if self.totp:
            params = {'act': '2fa'}
            data = {'2fa': self.totp}
            r = self.session.post(loginpage, params=params, data=data)
            if r.status_code != 200:
                raise LoginException
        accountinfo = self.request('index')
        self.authkey = accountinfo['authkey']
        self.passkey = accountinfo['passkey']
        self.userid = accountinfo['id']

    def logout(self):
        self.session.get('{0}/logout.php?auth={1}'.format(self.endpoint, self.authkey))

    def request(self, action, **kwargs):
        '''Makes an AJAX request at a given action page'''
        while time.time() - self.last_request < self.rate_limit:
            time.sleep(0.1)

        ajaxpage = '{0}/ajax.php'.format(self.endpoint)
        params = {'action': action}
        if self.authkey:
            params['auth'] = self.authkey
        params.update(kwargs)
        r = self.session.get(ajaxpage, params=params, allow_redirects=False)
        self.last_request = time.time()
        try:
            parsed = json.loads(r.content)
            if parsed['status'] != 'success':
                raise RequestException
            return parsed['response']
        except ValueError:
            raise RequestException

    def request_html(self, action, **kwargs):
        while time.time() - self.last_request < self.rate_limit:
            time.sleep(0.1)

        ajaxpage = '{0}action'.format(self.endpoint)
        if self.authkey:
            kwargs['auth'] = self.authkey
        r = self.session.get(ajaxpage, params=kwargs, allow_redirects=False)
        self.last_request = time.time()
        return r.content
    
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

    def get_candidates(self, mode, skip=None, media=lossless_media):
        if not media.issubset(lossless_media):
            raise ValueError('Unsupported media type {0}'.format((media - lossless_media).pop()))

        if not any(s == mode for s in ('snatched', 'uploaded', 'both', 'all', 'seeding')):
            raise ValueError('Unsupported candidate mode {0}'.format(mode))

        # gazelle doesn't currently support multiple values per query
        # parameter, so we have to search a media type at a time;
        # unless it's all types, in which case we simply don't specify
        # a 'media' parameter (defaults to all types).

        if media == lossless_media:
            media_params = ['']
        else:
            media_params = ['&media={0}'.format(media_search_map[m]) for m in media]

        pattern = re.compile(r'reportsv2\.php\?action=report&amp;id=(\d+)".*?torrents\.php\?id=(\d+)"', re.MULTILINE | re.IGNORECASE | re.DOTALL)
        if mode == 'snatched' or mode == 'both' or mode == 'all':
            url = '{0}/torrents.php?type=snatched&userid={1}&format=FLAC'.format(self.endpoint, self.userid)
            for mp in media_params:
                page = 1
                done = False
                while not done:
                    content = self.session.get(url + mp + "&page={0}".format(page)).text
                    for torrentid, groupid in pattern.findall(content):
                        if skip is None or torrentid not in skip:
                            yield int(groupid), int(torrentid)
                    done = 'Next &gt;' not in content
                    page += 1

        if mode == 'uploaded' or mode == 'both' or mode == 'all':
            url = '{0}/torrents.php?type=uploaded&userid={1}&format=FLAC'.format(self.endpoint, self.userid)
            for mp in media_params:
                page = 1
                done = False
                while not done:
                    content = self.session.get(url + mp + "&page={0}".format(page)).text
                    for torrentid, groupid in pattern.findall(content):
                        if skip is None or torrentid not in skip:
                            yield int(groupid), int(torrentid)
                    done = 'Next &gt;' not in content
                    page += 1

        if mode == 'seeding' or mode == 'all':
            url = '{0}/better.php?method=transcode&filter=seeding'.format(self.endpoint)
            pattern = re.compile('torrents.php\?groupId=(\d+)&torrentid=(\d+)#\d+')
            content = self.session.get(url).text
            for groupid, torrentid in pattern.findall(content):
                if skip is None or torrentid not in skip:
                    yield int(groupid), int(torrentid)

    def upload(self, group, torrent, new_torrent, format, description=[]):
        url = '{0}/upload.php?groupid={1}'.format(self.endpoint, group['group']['id'])
        self.session.open(url)
        form = self.session.select_form(selector='.create_form')

        # requests encodes using rfc2231 in python 3 which php doesn't understand
        files = {'file_input': ('1.torrent', open(new_torrent, 'rb'), 'application/x-bittorrent')}

        # MechanicalSoup 0.12.0+ now overwrites files with blank if a matching form field
        # exists and is not disabled.
        torrent_field = form.form.find('input', attrs={'id': 'file'})
        if torrent_field:
            torrent_field.attrs['disabled'] = 'disabled'

        if torrent['remastered']:
            form['remaster'] = True
            form['remaster_year'] = str(torrent['remasterYear'])
            form['remaster_title'] = torrent['remasterTitle']
            form['remaster_record_label'] = torrent['remasterRecordLabel']
            form['remaster_catalogue_number'] = torrent['remasterCatalogueNumber']
        else:
            form['remaster_year'] = ''
            form['remaster_title'] = ''
            form['remaster_record_label'] = ''
            form['remaster_catalogue_number'] = ''

        form['format'] = formats[format]['format']
        form['bitrate'] = formats[format]['encoding']
        form['media'] = torrent['media']

        release_desc = '\n'.join(description)
        if release_desc:
            form['release_desc'] = release_desc

        return self.session.submit_selected(files=files)

    def set_24bit(self, torrent):
        url = '{0}/torrents.php?action=edit&id={1}'.format(self.endpoint, torrent['id'])
        self.session.open(url)
        form = self.session.select_form(selector='.create_form')
        form['bitrate'] = '24bit Lossless'

        return self.session.submit_selected()

    def release_url(self, group, torrent):
        return '{0}/torrents.php?id={1}&torrentid={2}#torrent{3}'.format(self.endpoint, group['group']['id'], torrent['id'], torrent['id'])

    def permalink(self, torrent):
        return '{0}/torrents.php?torrentid={1}'.format(self.endpoint, torrent['id'])

    def get_better(self, type=3):
        p = re.compile(r'(torrents\.php\?action=download&(?:amp;)?id=(\d+)[^"]*).*(torrents\.php\?id=\d+(?:&amp;|&)torrentid=\2\#torrent\d+)', re.DOTALL)
        out = []
        data = self.request_html('better.php', method='transcode', type=type)
        for torrent, id, perma in p.findall(data):
            out.append({
                'permalink': perma.replace('&amp;', '&'),
                'id': int(id),
                'torrent': torrent.replace('&amp;', '&'),
            })
        return out

    def get_torrent(self, torrent_id):
        '''Downloads the torrent at torrent_id using the authkey and passkey'''
        while time.time() - self.last_request < self.rate_limit:
            time.sleep(0.1)

        torrentpage = '{0}/torrents.php'.format(self.endpoint)
        params = {'action': 'download', 'id': torrent_id}
        if self.authkey:
            params['authkey'] = self.authkey
            params['torrent_pass'] = self.passkey
        r = self.session.get(torrentpage, params=params, allow_redirects=False)

        self.last_request = time.time() + 2.0
        if r.status_code == 200 and 'application/x-bittorrent' in r.headers['content-type']:
            return r.content
        return None

    def get_torrent_info(self, id):
        return self.request('torrent', id=id)['torrent']

def unescape(text):
    return html.unescape(text)
