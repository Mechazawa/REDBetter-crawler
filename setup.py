#!/usr/bin/env python
'''
Installer script for whatbetter.
'''

from setuptools import setup

setup (
    name = "whatbetter",
    description = "Automatically transcode and upload FLACs on What.CD.",
    author = 'Zach Denton',
    author_email = 'zacharydenton@gmail.com',
    version = '1.0',
    url = 'http://github.com/zacharydenton/whatbetter',
    py_modules = ['mediafile',
                  'transcode',
                  'whatapi'],
    scripts = ['whatbetter'],
    install_requires = ['mutagen',
                'mechanize',
                'argparse',
                'ordereddict',
                'requests']
)
