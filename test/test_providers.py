from scrapy_poet.page_input_providers import providers
from scrapy_autoextract.providers import (
    ArticleDataProvider,
    ProductDataProvider,
    install,
)


PROVIDERS = (
    ArticleDataProvider,
    ProductDataProvider,
)


def test_install():
    # Given an uninitialized scrapy-poet repository,
    # our AutoExtract should not be registered by default
    for provider in PROVIDERS:
        assert providers.get(provider.provided_class) is None

    # After installing AutoExtract providers...
    install()

    # Our AutoExtract providers should be registered now
    for provider in PROVIDERS:
        assert providers.get(provider.provided_class) is provider
