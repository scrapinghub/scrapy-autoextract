#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages


def get_version():
    here = os.path.abspath(os.path.dirname(__file__))
    path = os.path.join(here, 'scrapy_autoextract', 'VERSION')
    with open(path) as f:
        return f.read().strip()


setup(
    name='scrapy-autoextract',
    version=get_version(),
    author='Scrapinghub Inc',
    author_email='info@scrapinghub.com',
    maintainer='Scrapinghub Inc',
    maintainer_email='info@scrapinghub.com',
    description='Scrapinghub AutoExtract API integration for Scrapy',
    long_description=open('README.rst').read(),
    url='https://github.com/scrapinghub/scrapy-autoextract',
    packages=find_packages(),
    package_data={'scrapy_autoextract': ['VERSION']},
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
        'Framework :: Scrapy',
    ],
)
