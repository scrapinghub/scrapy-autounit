import pickle
import zlib

from scrapy.crawler import Crawler
from scrapy.utils.conf import build_component_list
from scrapy.utils.project import get_project_settings

from .utils import get_spider_class


class Cassette:
    """
    Helper class to store request, response and output data.
    """
    FIXTURE_VERSION = 2

    def __init__(self, spider=None):
        if spider:
            self.spider_name = spider.name
            self.middlewares = self._get_middlewares(spider.settings)
            self.included_settings = self._get_included_settings(spider.settings)
        self.python_version = sys.version_info.major

        # Set by Recorder.new_cassette
        self.request = None
        self.response = None
        self.init_attrs = None
        self.input_attrs = None

        # Set by Recorder.record
        self.filename = None
        self.output_data = None
        self.output_attrs = None

    @classmethod
    def from_fixture(cls, fixture):
        with open(fixture, 'rb') as f:
            binary = f.read()
        cassette = pickle.loads(zlib.decompress(binary))
        return cassette

    def _get_middlewares(self, settings):
        full_list = build_component_list(settings.getwithbase('SPIDER_MIDDLEWARES'))
        autounit_mw_path = list(filter(lambda x: x.endswith('AutounitMiddleware'), full_list))[0]
        start = full_list.index(autounit_mw_path)
        mw_paths = [mw for mw in full_list[start:] if mw != autounit_mw_path]
        return mw_paths

    def _get_included_settings(self, settings):
        names = settings.getlist('AUTOUNIT_INCLUDED_SETTINGS', [])
        included = {name: settings.get(name) for name in names}
        return included

    def get_spider(self):
        settings = get_project_settings()
        spider_cls = get_spider_class(self.spider_name, settings)

        spider_cls.update_settings(settings)
        for k, v in self.included_settings.items():
            settings.set(k, v, priority=50)

        crawler = Crawler(spider_cls, settings)
        spider = spider_cls.from_crawler(crawler, **self.init_attrs)
        return spider

    def pack(self):
        return zlib.compress(pickle.dumps(self, protocol=2))

    def to_dict(self):
        return {
            'spider_name': self.spider_name,
            'request': self.request,
            'response': self.response,
            'output_data': self.output_data,
            'middlewares': self.middlewares,
            'settings': self.included_settings,
            'init_attrs': self.init_attrs,
            'input_attrs': self.input_attrs,
            'output_attrs': self.output_attrs,
        }
