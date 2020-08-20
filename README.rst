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


Usage
=====

There are two different ways to consume the AutoExtract API with this library:

* using our Scrapy middleware
* using our Page Object providers

The middleware
--------------

The middleware is opt-in and can be explicitly enabled per request,
with the ``{'autoextract': {'enabled': True}}`` request meta.
All the options below can be set either in the project settings file,
or just for specific spiders, in the ``custom_settings`` dict.

Within the spider, consuming the AutoExtract result is as easy as::

    def parse(self, response):
        yield response.meta['autoextract']

Configuration
^^^^^^^^^^^^^

Add the AutoExtract downloader middleware in the settings file::

    DOWNLOADER_MIDDLEWARES = {
        'scrapy_autoextract.AutoExtractMiddleware': 543,
    }

Note that this should be the last downloader middleware to be executed.

The providers
-------------

Another way of consuming AutoExtract API is using the Page Objects pattern
proposed by the `web-poet`_ library and implemented by `scrapy-poet`_.

Page Objects their returned Items are defined by the `autoextract-poet`_
library.

Within the spider, consuming the AutoExtract result is as easy as::

    from autoextract_poet.page_inputs import AutoExtractArticleData

    def parse(self, response, article: AutoExtractArticleData):
        yield article.to_item()

Configuration
^^^^^^^^^^^^^

First, you need to configure scrapy-poet as described on `scrapy-poet's documentation`_.
Then, enable AutoExtract providers by putting the following code to Scrapy's ``settings.py`` file::

    import scrapy_autoextract.providers
    scrapy_autoextract.providers.install()

Now you should be ready to use our AutoExtract providers.

Settings
========

Common settings
---------------

- ``AUTOEXTRACT_USER`` [mandatory] is your AutoExtract API key
- ``AUTOEXTRACT_URL`` [optional] the AutoExtract service url. Defaults to autoextract.scrapinghub.com.

Middleware settings
-------------------

- ``AUTOEXTRACT_TIMEOUT`` [optional] sets the response timeout from AutoExtract. Defaults to 660 seconds.
  Can also be defined by setting the "download_timeout" in the request.meta.
- ``AUTOEXTRACT_PAGE_TYPE`` [mandatory] defines the kind of document to be extracted.
  Current available options are `"product"` and `"article"`.
  Can also be defined on ``spider.page_type``, or ``{'autoextract': {'pageType': '...'}}`` request meta.
  This is required for the AutoExtract classifier to know what kind of page needs to be extracted.
- `extra` [optional] allows sending extra payload data to your AutoExtract request.
  Must be specified as ``{'autoextract': {'extra': {}}}`` request meta and must be a dict.
- ``AUTOEXTRACT_SLOT_POLICY`` [optional] Download concurrency options. Defaults to ``SlotPolicy.PER_DOMAIN``
  - If set to ``SlotPolicy.PER_DOMAIN``, then consider setting ``SCHEDULER_PRIORITY_QUEUE = 'scrapy.pqueues.DownloaderAwarePriorityQueue'``
  to make better usage of AutoExtract concurrency and avoid delays.

Provider settings
-----------------

- ``AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES`` [optional] Max number of retries for Query-level errors. Defaults to ``3``.

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
* 429 errors are handled as standard retries when using Scrapy middleware,
  but they're handled properly and automatically with scrapy-poet integration,
  as it relies on `scrapinghub-autoextract`_.
  You may loose some responses with the middleware.
  With scrapy-poet, there is no need to change ``RETRY_HTTP_CODES``.
* Overall, retries have a better behavior with scrapy-poet integration
  and it includes support for automatic Query-level errors retries

When using the AutoExtract providers, be aware that:

* With scrapy-poet integration, retry requests don't go through Scrapy
* Not all data types are supported with scrapy-poet,
  currently only Articles and Products are supported

.. _`web-poet`: https://github.com/scrapinghub/web-poet
.. _`scrapy-poet`: https://github.com/scrapinghub/scrapy-poet
.. _`autoextract-poet`: https://github.com/scrapinghub/autoextract-poet
.. _`scrapinghub-autoextract`: https://github.com/scrapinghub/scrapinghub-autoextract
.. _`scrapy-poet's documentation` https://scrapy-poet.readthedocs.io/en/latest/intro/tutorial.html#configuring-the-project
