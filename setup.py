#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages

NAME = 'scrapy-autoextract'


def get_version():
    about = {}
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, NAME.replace('-', '_'), '__version__.py')) as f:
        exec(f.read(), about)
    return about['__version__']


setup(
    name=NAME,
    version=get_version(),
    author='Scrapinghub Inc',
    author_email='info@scrapinghub.com',
    maintainer='Scrapinghub Inc',
    maintainer_email='info@scrapinghub.com',
    description='Scrapinghub AutoExtract API integration for Scrapy',
    long_description=open('README.rst').read(),
    url='https://github.com/scrapinghub/scrapy-autoextract',
    packages=find_packages(),
    install_requires=[
        'autoextract-poet>=0.2.0',
        'scrapinghub-autoextract>=0.6.0',
        'scrapy-poet>=0.1.0',
        'aiohttp',
        'tldextract',
    ],
    keywords='scrapy autoextract middleware',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Framework :: Scrapy',
    ],
)
