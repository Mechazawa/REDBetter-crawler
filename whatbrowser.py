#!/usr/bin/env python
import mechanize

class WhatBrowser(mechanize.Browser):
    def __init__(self, username, password):
        super(WhatBrowser, self).__init__()

        self.set_handle_robots(False) # ignore robots.txt
        self.open('http://what.cd/login.php')

        self.select_form(nr=0)
        self['username'] = username
        self['password'] = password
        response = self.submit()

    def get_release_info(self, release_url):
        pass
