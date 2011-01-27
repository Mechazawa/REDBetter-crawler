#!/usr/bin/env python
'''
Installer script for whatbetter.
'''

from distutils.core import setup

setup (
    name = "whatbetter",
    description = "Automatically transcode and upload FLACs on What.CD.",
    author = 'Zach Denton',
    author_email = 'zacharydenton@gmail.com',
    version = '1.0',
    url = 'http://zacharydenton.com/code/whatbetter/',
    py_modules = ['mediafile',
                  'transcode',
                  'whatbrowser',
                  'ordereddict'],
    scripts = ['whatbetter'],
    requires = ['mutagen',
                'mechanize',
                'argparse',
                'BeautifulSoup',
                'lxml']
)
