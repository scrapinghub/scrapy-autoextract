Changes
=======

0.7.0 (2021-08-04)
------------------

* Support for all Automatic Extraction API page types by upgrading to
  ``autoextract-poet`` 0.3.0
* Rename Scrapinghub references to Zyte
* Update README

0.6.1 (2021-06-02)
------------------

* A cache of AutoExtract requests can now be enabled by
  setting ``AUTOEXTRACT_CACHE_FILENAME``.

0.6.0 (2021-06-01)
------------------
* Switch from ``scrapinghub-autoextract`` to ``zyte-autoextract`` package,
  following its rename.
* Upgrade ``scrapy-poet`` to 0.2.0+.

Note that the switch is backwards incompatible if you're
relying on ``SCRAPINHUB_AUTOEXTRACT_KEY`` environment variable
to set an API key; it is no longer working. Please use
either ``ZYTE_ATOEXTRACT_KEY`` env variable or ``AUTOEXTRACT_USER``
setting instead.

0.5.2 (2021-01-27)
------------------

* Upgrade ``autoextract-poet`` to 0.2.1
* Upgrade ``scrapinghub-autoextract`` to 0.6.1

0.5.1 (2021-01-22)
------------------
* AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES default value is set to 0, to account
  for backend changes in AutoExtract API.

0.5.0 (2021-01-21)
------------------

* Mayor internal and API refactor. No backwards compatible.
* Support for the new ``autoextract-poet`` 0.2.0 types.
* Use of the new providers interface introduced in ``scrapy-poet``  0.1.0
* ``scrapinghub-autoextract`` AutoExtract client updated to 0.6.0
* CI is moved from Travis to Github Actions.
* Python 3.9 support.
