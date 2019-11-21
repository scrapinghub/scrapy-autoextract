====================================
Scrapy & Autoextract API integration
====================================

.. image:: https://img.shields.io/pypi/v/scrapy-autoextract.svg
   :target: https://pypi.org/project/scrapy-autoextract/
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/scrapy-autoextract.svg
    :target: https://pypi.org/project/scrapy-autoextract/
    :alt: Supported Python Versions

.. image:: https://travis-ci.org/scrapinghub/scrapy-autoextract.svg?branch=master
    :target: https://travis-ci.org/scrapinghub/scrapy-autoextract
    :alt: Build Status


This library integrates ScrapingHub's AI Enabled Automatic Data Extraction
into a Scrapy spider using a downloader middleware.
The middleware adds the result of AutoExtract to ``response.meta['autoextract']``
for consumption by the spider.


Installation
============

::

    pip install scrapy-autoextract

scrapy-autoextract requires Python 3.5+


Configuration
=============

Add the AutoExtract downloader middleware in the settings file::

    DOWNLOADER_MIDDLEWARES = {
        'scrapy_autoextract.AutoExtractMiddleware': 543,
    }

Note that this should be the last downloader middleware to be executed.


Usage
=====

The middleware is opt-in and can be explicitly enabled per request,
with the ``{'autoextract': {'enabled': True}}`` request meta.
All the options below can be set either in the project settings file,
or just for specific spiders, in the ``custom_settings`` dict.

Available settings:

- ``AUTOEXTRACT_USER`` [mandatory] is your AutoExtract API key
- ``AUTOEXTRACT_URL`` [optional] the AutoExtract service url. Defaults to autoextract.scrapinghub.com.
- ``AUTOEXTRACT_TIMEOUT`` [optional] sets the response timeout from AutoExtract. Defaults to 660 seconds.
  Can also be defined by setting the "download_timeout" in the request.meta.
- ``AUTOEXTRACT_PAGE_TYPE`` [mandatory] defines the kind of document to be extracted.
  Current available options are `"product"` and `"article"`.
  Can also be defined on ``spider.page_type``, or ``{'autoextract': {'pageType': '...'}}`` request meta.
  This is required for the AutoExtract classifier to know what kind of page needs to be extracted.
- `extra` [optional] allows sending extra payload data to your AutoExtract request.
  Must be specified as ``{'autoextract': {'extra': {}}}`` request meta and must be a dict.


Within the spider, consuming the AutoExtract result is as easy as::

    def parse(self, response):
        yield response.meta['autoextract']


Limitations
===========

When using the AutoExtract middleware, there are some limitations.

* The incoming spider request is rendered by AutoExtract, not just downloaded by Scrapy,
  which can change the result - the IP is different, headers are different, etc.
* Only GET requests are supported
* Custom headers and cookies are not supported (i.e. Scrapy features to set them don't work)
* Proxies are not supported (they would work incorrectly,
  sitting between Scrapy and AutoExtract, instead of AutoExtract and website)
* AutoThrottle extension can work incorrectly for AutoExtract requests,
  because AutoExtract timing can be much larger than time required to download a page,
  so it's best to use ``AUTHTHROTTLE_ENABLED=False`` in the settings.
* Redirects are handled by AutoExtract, not by Scrapy,
  so these kinds of middlewares might have no effect
* Retries should be disabled, because AutoExtract handles them internally
  (use ``RETRY_ENABLED=False`` in the settings)
  There is an exception, if there are too many requests sent in
  a short amount of time and AutoExtract returns HTTP code 429.
  For that case it's best to use ``RETRY_HTTP_CODES=[429]``.
