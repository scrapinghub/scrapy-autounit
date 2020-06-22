import zlib
import pickle

from scrapy.utils.conf import build_component_list

from .utils import python_version


class Cassette:
    """
    Helper class to store request, response and output data.
    """
    FIXTURE_VERSION = 2

    def __init__(self, spider):
        self.spider_name = spider.name
        self._get_middlewares(spider.settings)
        self._get_included_settings(spider.settings)
        self.python_version = python_version()

        # Set by Recorder.new_cassette
        self.request = None
        self.response = None
        self.init_attrs = None
        self.input_attrs = None

        # Set by Recorder.record
        self.output_data = None
        self.output_attrs = None

    @classmethod
    def from_fixture(cls, fixture):
        with open(fixture, 'rb') as f:
            binary = f.read()
        cassette = pickle.loads(zlib.decompress(binary))
        return cassette

    def _get_middlewares(self, settings):
        full_list = build_component_list(
            settings.getwithbase('SPIDER_MIDDLEWARES'))
        autounit_mw_path = list(filter(
            lambda x: x.endswith('AutounitMiddleware'), full_list))[0]
        start = full_list.index(autounit_mw_path)
        mw_paths = [mw for mw in full_list[start:] if mw != autounit_mw_path]
        self.middlewares = mw_paths

    def _get_included_settings(self, settings):
        names = settings.getlist(
            'AUTOUNIT_INCLUDED_SETTINGS', [])
        included = {name: settings.get(name) for name in names}
        self.included_settings = included

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
            'input_attrs': self.input_attrs,
            'output_attrs': self.output_attrs,
        }
