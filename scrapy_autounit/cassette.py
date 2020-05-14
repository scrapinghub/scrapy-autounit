import six
import copy
import zlib
import pickle

from scrapy.crawler import Crawler
from scrapy.spiders import CrawlSpider
from scrapy.http import Request, Response
from scrapy.utils.reqser import request_to_dict
from scrapy.utils.conf import build_component_list
from scrapy.utils.project import get_project_settings
from scrapy.commands.genspider import sanitize_module_name

from .utils import get_spider_class, get_spider_attrs


class Cassette:
    FIXTURE_VERSION = 1

    def __init__(self, response, spider, init_attrs):
        self.spider = spider
        self.spider_name = spider.name
        self.safe_spider_name = sanitize_module_name(spider.name)
        self.crawler = spider.crawler
        self.settings = spider.settings
        self.included_settings = self._get_included_settings()
        self.request = self._request_to_dict(response.request)
        self.response = self._response_to_dict(response)
        self.init_attrs = init_attrs
        self.spider_args_in = get_spider_attrs(spider)
        self.spider_args_out = {}
        self.result = []
        self.middlewares = self._get_middlewares()
        self.python_version = 2 if six.PY2 else 3

    @classmethod
    def from_fixture(cls, fixture):
        with open(fixture, 'rb') as f:
            binary = f.read()
        cassette = pickle.loads(zlib.decompress(binary))
        settings = get_project_settings()
        spider_cls = get_spider_class(cassette.spider_name, settings)
        spider_cls.update_settings(settings)
        for k, v in cassette.included_settings.items():
            settings.set(k, v, priority=50)
        crawler = Crawler(spider_cls, settings)
        spider = spider_cls.from_crawler(
            crawler, **cassette.spider_args_in)
        crawler.spider = spider

        cassette.spider = spider
        cassette.crawler = crawler
        cassette.settings = settings
        return cassette

    def _get_middlewares(self):
        full_list = build_component_list(
            self.settings.getwithbase('SPIDER_MIDDLEWARES'))
        autounit_mw_path = list(filter(
            lambda x: x.endswith('AutounitMiddleware'), full_list))[0]
        start = full_list.index(autounit_mw_path)
        mw_paths = [mw for mw in full_list[start:] if mw != autounit_mw_path]
        return mw_paths

    def _clean_headers(self, headers):
        excluded = self.settings.get('AUTOUNIT_EXCLUDED_HEADERS', default=[])
        auth_headers = ['Authorization', 'Proxy-Authorization']
        included = self.settings.get(
            'AUTOUNIT_INCLUDED_AUTH_HEADERS', default=[])
        excluded.extend([h for h in auth_headers if h not in included])
        for header in excluded:
            headers.pop(header, None)
            headers.pop(header.encode(), None)

    def _request_to_dict(self, request):
        _request = request_to_dict(request, spider=self.spider)
        if not _request['callback']:
            _request['callback'] = 'parse'
        elif isinstance(self.spider, CrawlSpider):
            rule = request.meta.get('rule')
            if rule is not None:
                _request['callback'] = self.spider.rules[rule].callback
        self._clean_headers(_request['headers'])
        _meta = {}
        for key, value in _request.get('meta').items():
            if key != '_autounit_cassette':
                _meta[key] = self.parse_object(value)
        _request['meta'] = _meta
        return _request

    def _response_to_dict(self, response):
        return {
            'cls': '{}.{}'.format(
                type(response).__module__,
                getattr(type(response), '__qualname__', None) or
                getattr(type(response), '__name__', None)
            ),
            'url': response.url,
            'status': response.status,
            'body': response.body,
            'headers': dict(response.headers),
            'flags': response.flags,
            'encoding': response.encoding,
        }

    def _get_included_settings(self):
        out = {}
        for name in self.settings.getlist('AUTOUNIT_INCLUDED_SETTINGS', []):
            out[name] = self.settings.get(name)
        return out

    def pack(self):
        del self.crawler, self.spider, self.settings
        return zlib.compress(
            pickle.dumps(self, protocol=2)
        )

    def parse_object(self, _object):
        if isinstance(_object, Request):
            return self._request_to_dict(_object)
        elif isinstance(_object, Response):
            return self.parse_object(self._response_to_dict(_object))
        elif isinstance(_object, dict):
            for k, v in _object.items():
                _object[k] = self.parse_object(v)
        elif isinstance(_object, (list, tuple)):
            for i, v in enumerate(_object):
                _object[i] = self.parse_object(v)
        return _object

    def parse_callback_result(self, result):
        out = []
        for elem in result:
            out.append(elem)
            is_request = isinstance(elem, Request)
            if is_request:
                data = self._request_to_dict(elem)
            else:
                data = self.parse_object(copy.deepcopy(elem))
            self.result.append({
                'type': 'request' if is_request else 'item',
                'data': data
            })
        self.spider_args_out = get_spider_attrs(self.spider)
        return out

    def to_dict(self):
        return dict(
            spider_name=self.spider_name,
            request=self.request,
            response=self.response,
            spider_args_in=self.spider_args_in,
            spider_args_out=self.spider_args_out,
            result=self.result,
            settings=self.settings,
            middlewares=self.middlewares,
            python_version=self.python_version,
        )
