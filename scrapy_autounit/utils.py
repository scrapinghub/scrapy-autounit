from itertools import islice

from scrapy.spiders import CrawlSpider
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes


def get_spider_class(spider_name, project_settings):
    spider_modules = project_settings.get('SPIDER_MODULES')
    for spider_module in spider_modules:
        modules = walk_modules(spider_module)
        for module in islice(modules, 1, None):
            for spider_class in iter_spider_classes(module):
                if spider_class.name == spider_name:
                    return spider_class
    return None


def get_spider_attrs(spider):
    filter_attrs = {'crawler', 'settings', 'start_urls'}
    if isinstance(spider, CrawlSpider):
        filter_attrs |= {'rules', '_rules'}
    return {
        k: v for k, v in spider.__dict__.items()
        if k not in filter_attrs
    }
