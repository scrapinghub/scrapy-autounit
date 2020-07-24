import os
from importlib import import_module
from itertools import islice

from scrapy.utils.conf import closest_scrapy_cfg, init_env
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes


def get_base_path(settings):
    return settings.get(
        'AUTOUNIT_BASE_PATH',
        default=os.path.join(get_project_dir(), 'autounit')
    )


def get_project_dir():
    closest_cfg = closest_scrapy_cfg()
    if closest_cfg:
        return os.path.dirname(closest_cfg)

    init_env()
    scrapy_module = os.environ.get('SCRAPY_SETTINGS_MODULE')
    if scrapy_module is None:
        return None

    try:
        module = import_module(scrapy_module)
        return os.path.dirname(os.path.dirname(module.__file__))
    except ImportError:
        return None


def get_spider_class(spider_name, project_settings):
    spider_modules = project_settings.get('SPIDER_MODULES')
    for spider_module in spider_modules:
        modules = walk_modules(spider_module)
        for module in islice(modules, 1, None):
            for spider_class in iter_spider_classes(module):
                if spider_class.name == spider_name:
                    return spider_class
    return None


def generate_test(fixture_path, encoding='utf-8'):
    raise AssertionError(
        "This spider's tests and fixtures are from an old version and need to be updated. "
        "Please update them by using the `autounit` command line utility. "
        "See `autounit update -h` for more help.")
