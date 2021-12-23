import os

from tldextract import tldextract
from scrapy.utils.project import inside_project, project_data_dir


def get_domain(url):
    """
    Return the domain without any subdomain

    >>> get_domain("http://blog.example.com")
    'example.com'
    >>> get_domain("http://www.example.com")
    'example.com'
    >>> get_domain("http://deeper.blog.example.co.uk")
    'example.co.uk'
    """
    return ".".join(tldextract.extract(url)[-2:])


def get_scrapy_data_path(createdir=True):
    """ Return a path to a folder where Scrapy is storing data.
    Usually that's a .scrapy folder inside the project.
    """
    # This code is extracted from scrapy.utils.project.data_path function,
    # which does too many things.
    path = project_data_dir() if inside_project() else ".scrapy"
    if createdir:
        os.makedirs(path, exist_ok=True)
    return path


def get_collection_name(provider):
    from_settings = provider.settings.get('AUTOEXTRACT_CACHE_COLLECTION_NAME')
    scrapy_job = os.environ.get('SCRAPY_JOB')
    if from_settings:
        return from_settings
    elif scrapy_job:
        return f"{scrapy_job.replace('/', '_')}_cache"
    return 'dev_cache'


def get_project_from_job():
    scrapy_job = os.environ.get('SCRAPY_JOB')
    if scrapy_job:
        return scrapy_job.split('/')[0]
