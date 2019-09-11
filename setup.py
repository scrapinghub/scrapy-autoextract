from setuptools import setup, find_packages

setup(
    name='scrapy-autoextract',
    version='0.1',
    author='Scrapinghub Inc',
    description='Scrapinghub AutoExtract API integration for Scrapy',
    long_description=open('README.rst').read(),
    url='https://github.com/scrapinghub/scrapy-autoextract-middleware',
    packages=find_packages(),
)
