import logging
import secrets

from scrapy import signals
from scrapy.exceptions import NotConfigured

from .recorder import Recorder


logger = logging.getLogger(__name__)


class AutounitMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler
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

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler)
        crawler.signals.connect(
            mw.engine_started, signal=signals.engine_started)
        return mw

    def engine_started(self):
        self.recorder = Recorder(self.crawler.spider)

    def process_spider_input(self, response, spider):
        cassette = self.recorder.new_cassette(response)
        response.meta['_autounit_cassette'] = cassette
        return None

    def process_spider_output(self, response, result, spider):
        cassette = response.meta.pop('_autounit_cassette')
        out = self.recorder.record(cassette, result)
        return out
