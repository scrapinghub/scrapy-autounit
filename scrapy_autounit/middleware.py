import logging

from scrapy.exceptions import NotConfigured

from .cassette import Cassette
from .recorder import Recorder
from .utils import get_spider_attrs


logger = logging.getLogger(__name__)


class AutounitMiddleware:
    def __init__(self, crawler):
        settings = crawler.settings

        spider_mw = settings.getwithbase('SPIDER_MIDDLEWARES').keys()
        if not any(self.__class__.__name__ in mw for mw in spider_mw):
            raise ValueError(
                '{} must be in SPIDER_MIDDLEWARES'.format(
                    self.__class__.__name__))

        if not settings.getbool('AUTOUNIT_ENABLED'):
            raise NotConfigured('scrapy-autounit is not enabled')

        if settings.getint('CONCURRENT_REQUESTS') > 1:
            logger.warn(
                'Recording with concurrency > 1! '
                'Data races in shared object modification may create broken '
                'tests.')

        self.recorder = Recorder(crawler)
        self.init_attrs = get_spider_attrs(crawler.spider)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_spider_input(self, response, spider):
        response.meta['_autounit_cassette'] = Cassette(
            response, spider, self.init_attrs)
        return None

    def process_spider_output(self, response, result, spider):
        cassette = response.meta.pop('_autounit_cassette')
        out = cassette.parse_callback_result(result)
        self.recorder.record(cassette)
        return out
