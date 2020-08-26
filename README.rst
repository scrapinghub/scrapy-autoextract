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

scrapy-autoextract requires Python 3.6+


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

    import scrapy
    from autoextract_poet.page_inputs import AutoExtractArticleData

    class SampleSpider(scrapy.Spider):

        name = "sample"

        def parse(self, response, article: AutoExtractArticleData):
            # We're making two requests here:
            # - one through Scrapy to build the response argument
            # - another through providers to build the article argument
            yield article.to_item()

Note that on the example above, we're going to perform two requests:

* one goes through Scrapy (it might use Crawlera, Splash or no proxy at all, depending on your configuration)
* another goes through AutoExtract API using `scrapinghub-autoextract`_

If you don't need the additional request going through Scrapy,
you can annotate the response argument of your callback with ``DummyResponse``.
This will ignore the Scrapy request and only the AutoExtract API will be fetched.

For example::

    import scrapy
    from autoextract_poet.page_inputs import AutoExtractArticleData
    from scrapy_poet.utils import DummyResponse

    class SampleSpider(scrapy.Spider):

        name = "sample"

        def parse(self, response: DummyResponse, article: AutoExtractArticleData):
            # We're making a single request here to build the article argument
            yield article.to_item()

Configuration
^^^^^^^^^^^^^

First, you need to configure scrapy-poet as described on `scrapy-poet's documentation`_
and then enable AutoExtract providers by putting the following code to Scrapy's ``settings.py`` file::

    # Install AutoExtract providers
    import scrapy_autoextract.providers
    scrapy_autoextract.providers.install()

    # Enable scrapy-poet's provider injection middleware
    DOWNLOADER_MIDDLEWARES = {
        'scrapy_poet.InjectionMiddleware': 543,
    }

    # Configure Twisted's reactor for asyncio support on Scrapy
    TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'

Currently, our providers are implemented using asyncio.
Scrapy has introduced asyncio support since version 2.0
but as of Scrapy 2.3 you need to manually enable it by configuring Twisted's default reactor.
Check `Scrapy's asyncio documentation`_ for more information.

Checklist:

* scrapy-poet is installed and downloader/injector middleware is configured
* autoextract-poet is installed (page inputs are imported from this lib)
* providers are installed on settings.py
* Scrapy's asyncio support is enabled on settings.py

Now you should be ready to use our AutoExtract providers.

Exceptions
^^^^^^^^^^

While trying to fetch AutoExtract API, providers might raise some exceptions.
Those exceptions will probably come from `scrapinghub-autoextract`_
or Tenacity, the library used to implement retries.
For example:

* ``autoextract.aio.errors.RequestError``: raised when a `Request-level error`_ is returned
* ``autoextract.aio.errors.QueryRetryError``: raised when it's not possible to retry a `Query-level error`_
* ``tenacity.RetryError``: raised when it's not possible to retry an error

Check `scrapinghub-autoextract's async errors`_ for exception definitions.

You can capture those exceptions using an error callback (``errback``)::

    import scrapy
    from autoextract.aio.errors import RequestError, QueryRetryError
    from tenacity import RetryError
    from twisted.python.failure import Failure

    class SampleSpider(scrapy.Spider):

        name = "sample"
        urls = [...]

        def start_requests(self):
            for url in self.urls:
                yield scrapy.Request(url, callback=self.parse_article, errback=self.errback_article)

        def parse_article(self, response: DummyResponse, article: AutoExtractArticleData):
            yield article.to_item()

        def errback_article(self, failure: Failure):
            if failure.check(RequestError):
                self.logger.error(f"RequestError on {failure.request.url})

            if failure.check(QueryRetryError):
                self.logger.error(f"QueryRetryError on {failure.request.url})

            if failure.check(RetryError):
                self.logger.error(f"RetryError on {failure.request.url})

See `Scrapy documentation <https://docs.scrapy.org/en/latest/topics/request-response.html#using-errbacks-to-catch-exceptions-in-request-processing>`_
for more details on how to capture exceptions using request's errback.

Settings
========

Middleware settings
-------------------

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
- ``AUTOEXTRACT_SLOT_POLICY`` [optional] Download concurrency options. Defaults to ``SlotPolicy.PER_DOMAIN``
  - If set to ``SlotPolicy.PER_DOMAIN``, then consider setting ``SCHEDULER_PRIORITY_QUEUE = 'scrapy.pqueues.DownloaderAwarePriorityQueue'``
  to make better usage of AutoExtract concurrency and avoid delays.

Provider settings
-----------------

- ``AUTOEXTRACT_USER`` [optional] is your AutoExtract API key. Defaults to ``SCRAPINGHUB_AUTOEXTRACT_KEY`` environment variable.
- ``AUTOEXTRACT_URL`` [optional] the AutoExtract service url. Defaults to autoextract.scrapinghub.com.
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
* AutoExtract doesn't handle retries internally, they should be handled by its clients.
* 429 errors could be handled as standard retries when using Scrapy middleware,
  but they're handled properly and automatically with scrapy-poet integration,
  as it relies on `scrapinghub-autoextract`_.
  You may lose some responses with the middleware approach.
* Overall, retries have a better behavior with scrapy-poet integration
  and it includes support for automatic Query-level errors retries with
  no need to change ``RETRY_HTTP_CODES``.

When using the AutoExtract providers, be aware that:

* With scrapy-poet integration, retry requests don't go through Scrapy
* Not all data types are supported with scrapy-poet,
  currently only Articles and Products are supported

.. _`web-poet`: https://github.com/scrapinghub/web-poet
.. _`scrapy-poet`: https://github.com/scrapinghub/scrapy-poet
.. _`autoextract-poet`: https://github.com/scrapinghub/autoextract-poet
.. _`scrapinghub-autoextract`: https://github.com/scrapinghub/scrapinghub-autoextract
.. _`scrapinghub-autoextract's async errors`: https://github.com/scrapinghub/scrapinghub-autoextract/blob/master/autoextract/aio/errors.py
.. _`scrapy-poet's documentation` https://scrapy-poet.readthedocs.io/en/latest/intro/tutorial.html#configuring-the-project
.. _`Scrapy's asyncio documentation` https://docs.scrapy.org/en/latest/topics/asyncio.html
.. _`Request-level error`: https://doc.scrapinghub.com/autoextract.html#request-level
.. _`Query-level error`: https://doc.scrapinghub.com/autoextract.html#query-level
