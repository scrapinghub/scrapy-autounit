import os
import pickle
import sys
import zlib
from importlib import import_module
from itertools import islice
from pathlib import Path

import six
from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse, Request, Response
from scrapy.item import Item
from scrapy.utils.conf import (build_component_list, closest_scrapy_cfg,
                               init_env)
from scrapy.utils.misc import arg_to_iter, load_object, walk_modules
from scrapy.utils.project import get_project_settings
from scrapy.utils.python import to_bytes
from scrapy.utils.reqser import request_from_dict, request_to_dict
from scrapy.utils.spider import iter_spider_classes

import datadiff.tools

NO_ITEM_MARKER = object()


def create_instance(objcls, settings, crawler, *args, **kwargs):
    if settings is None:
        if crawler is None:
            raise ValueError("Specifiy at least one of settings and crawler.")
        settings = crawler.settings
    if crawler and hasattr(objcls, 'from_crawler'):
        return objcls.from_crawler(crawler, *args, **kwargs)
    elif hasattr(objcls, 'from_settings'):
        return objcls.from_settings(settings, *args, **kwargs)
    else:
        return objcls(*args, **kwargs)


def get_project_dir():
    closest_cfg = closest_scrapy_cfg()
    if closest_cfg:
        return Path(closest_cfg).parent

    init_env()
    scrapy_module = os.environ.get('SCRAPY_SETTINGS_MODULE')
    if scrapy_module is None:
        return None

    try:
        module = import_module(scrapy_module)
        return Path(module.__file__).parent.parent
    except ImportError:
        return None


def get_middlewares(spider):
    autounit_mw_path = 'scrapy_autounit.AutounitMiddleware'

    full_list = build_component_list(
        spider.settings.getwithbase('SPIDER_MIDDLEWARES'))
    start = full_list.index(autounit_mw_path)
    mw_paths = [mw for mw in full_list[start:] if mw != autounit_mw_path]

    return mw_paths


def create_dir(path, parents=False, exist_ok=False):
    try:
        Path.mkdir(path, parents=parents)
    except OSError:
        if not exist_ok:
            raise


def get_or_create_test_dir(base_path, spider_name, callback_name, extra=None):
    components = [base_path, 'tests', spider_name]
    if extra:
        components.append(extra)
    components.append(callback_name)
    test_dir = None
    for component in components:
        test_dir = test_dir / component if test_dir else component
        create_dir(test_dir, parents=True, exist_ok=True)
        (test_dir / '__init__.py').touch()
    test_name = '__'.join(components[2:])
    return test_dir, test_name


def add_sample(index, test_dir, test_name, data):
    url = data['request']['url']
    encoding = data['response']['encoding']
    fixture_name = 'fixture%s' % str(index)
    filename = fixture_name + '.bin'
    path = test_dir / filename
    data = compress_data(pickle_data(data))
    with open(str(path), 'wb') as outfile:
        outfile.write(data)
    write_test(test_dir, test_name, fixture_name, encoding, url)


def compress_data(data):
    return zlib.compress(data)


def decompress_data(data):
    return zlib.decompress(data)


def pickle_data(data):
    return pickle.dumps(data, protocol=2)


def unpickle_data(data, encoding):
    if six.PY2:
        return pickle.loads(data)
    return pickle.loads(data, encoding=encoding)


def response_to_dict(response):
    return {
        'url': response.url,
        'status': response.status,
        'body': response.body,
        'headers': dict(response.headers),
        'flags': response.flags,
        'encoding': response.encoding,
    }


def get_spider_class(spider_name, project_settings):
    spider_modules = project_settings.get('SPIDER_MODULES')
    for spider_module in spider_modules:
        modules = walk_modules(spider_module)
        for module in islice(modules, 1, None):
            for spider_class in iter_spider_classes(module):
                if spider_class.name == spider_name:
                    return spider_class
    return None


def parse_object(_object, spider):
    if isinstance(_object, Request):
        return parse_request(_object, spider)
    elif isinstance(_object, Response):
        return parse_object(response_to_dict(_object), spider)
    elif isinstance(_object, dict):
        return {k: parse_object(v, spider) for k, v in _object.items()}
    elif isinstance(_object, (list, tuple)):
        return [parse_object(v, spider) for v in _object]
    else:
        return _object


def parse_request(request, spider):
    _request = request_to_dict(request, spider=spider)
    if not _request['callback']:
        _request['callback'] = 'parse'

    clean_headers(_request['headers'], spider.settings)

    _meta = {}
    for key, value in _request.get('meta').items():
        if key != '_autounit':
            _meta[key] = parse_object(value, spider)
    _request['meta'] = _meta

    return _request


def clean_request(request, settings):
    _clean(request, settings, 'AUTOUNIT_REQUEST_SKIPPED_FIELDS')


def clean_headers(headers, settings):
    excluded = settings.get('AUTOUNIT_EXCLUDED_HEADERS', default=[])
    auth_headers = ['Authorization', 'Proxy-Authorization']
    included = settings.get('AUTOUNIT_INCLUDED_AUTH_HEADERS', default=[])
    excluded.extend([h for h in auth_headers if h not in included])
    for header in excluded:
        headers.pop(header, None)
        headers.pop(header.encode(), None)


def clean_item(item, settings):
    _clean(item, settings, 'AUTOUNIT_SKIPPED_FIELDS')


def _clean(data, settings, name):
    fields = settings.get(name, default=[])
    for field in fields:
        data.pop(field, None)


def write_test(path, test_name, fixture_name, encoding, url):
    command = 'scrapy {}'.format(' '.join(sys.argv))
    test_path = path / ('test_%s.py' % (fixture_name))

    test_code = '''# THIS IS A GENERATED FILE
# Generated by: {command}  # noqa: E501
# Request URL: {url}  # noqa: E501

import unittest
from pathlib import Path
from scrapy_autounit.utils import generate_test


class AutoUnit(unittest.TestCase):
    def test__{test_name}__{fixture_name}(self):
        self.maxDiff = None
        file_path = (
            Path(__file__).parent / '{fixture_name}.bin'
        )
        test = generate_test(file_path.resolve(), '{encoding}')
        test(self)


if __name__ == '__main__':
    unittest.main()
'''.format(
        test_name=test_name,
        fixture_name=fixture_name,
        encoding=encoding,
        command=command,
        url=url,
    )

    with open(str(test_path), 'w') as f:
        f.write(test_code)


def binary_check(fx_obj, cb_obj, encoding):
    if isinstance(cb_obj, (dict, Item)):
        fx_obj = {
            key: binary_check(value, cb_obj[key], encoding)
            for key, value in fx_obj.items()
        }

    if isinstance(cb_obj, list):
        fx_obj = [
            binary_check(fxitem, cbitem, encoding)
            for fxitem, cbitem in zip(fx_obj, cb_obj)
        ]

    if isinstance(cb_obj, Request):
        headers = {}
        for key, value in fx_obj['headers'].items():
            key = to_bytes(key, encoding)
            headers[key] = [to_bytes(v, encoding) for v in value]
        fx_obj['headers'] = headers
        fx_obj['body'] = to_bytes(fx_obj['body'], encoding)

    if isinstance(cb_obj, six.binary_type):
        fx_obj = fx_obj.encode(encoding)

    return fx_obj


def set_spider_attrs(spider, _args):
    for k, v in _args.items():
        setattr(spider, k, v)


def generate_test(fixture_path, encoding='utf-8'):
    with open(str(fixture_path), 'rb') as f:
        data = f.read()

    data = unpickle_data(decompress_data(data), encoding)

    spider_name = data.get('spider_name')
    if not spider_name:  # legacy tests
        spider_name = fixture_path.parent.parent.name

    settings = get_project_settings()

    spider_cls = get_spider_class(spider_name, settings)
    spider_cls.update_settings(settings)
    for k, v in data.get('settings', {}).items():
        settings.set(k, v, 50)

    crawler = Crawler(spider_cls, settings)
    spider = spider_cls.from_crawler(crawler, **data.get('spider_args_in'))
    crawler.spider = spider

    def test(self):
        fx_result = data['result']
        fx_version = data.get('python_version')

        set_spider_attrs(spider, data.get('spider_args_in'))
        request = request_from_dict(data['request'], spider)
        response = HtmlResponse(request=request, **data['response'])

        middlewares = []
        middleware_paths = data['middlewares']
        for mw_path in middleware_paths:
            try:
                mw_cls = load_object(mw_path)
                mw = create_instance(mw_cls, settings, crawler)
                middlewares.append(mw)
            except NotConfigured:
                continue

        crawler.signals.send_catch_log(
            signal=signals.spider_opened,
            spider=spider
        )
        result_attr_in = {
            k: v for k, v in spider.__dict__.items()
            if k not in ('crawler', 'settings', 'start_urls')
        }
        self.assertEqual(data['spider_args_in'], result_attr_in, 'Not equal!')

        for mw in middlewares:
            if hasattr(mw, 'process_spider_input'):
                mw.process_spider_input(response, spider)

        result = arg_to_iter(request.callback(response))
        middlewares.reverse()

        for mw in middlewares:
            if hasattr(mw, 'process_spider_output'):
                result = mw.process_spider_output(response, result, spider)

        for index, (cb_obj, fx_item) in enumerate(six.moves.zip_longest(
            result, fx_result, fillvalue=NO_ITEM_MARKER
        )):
            if any(item == NO_ITEM_MARKER for item in (cb_obj, fx_item)):
                raise AssertionError(
                    "The fixture's data length doesn't match with "
                    "the current callback's output length."
                )

            cb_obj = parse_object(cb_obj, spider)

            fx_obj = fx_item['data']
            if fx_item['type'] == 'request':
                clean_request(fx_obj, settings)
                clean_request(cb_obj, settings)
            else:
                clean_item(fx_obj, settings)
                clean_item(cb_obj, settings)

            if fx_version == 2 and six.PY3:
                fx_obj = binary_check(fx_obj, cb_obj, encoding)

            try:
                datadiff.tools.assert_equal(fx_obj, cb_obj)
            except AssertionError as e:
                six.raise_from(
                    AssertionError(
                        "Callback output #{} doesn't match recorded "
                        "output:{}".format(index, e)),
                    None)

        # Spider attributes get updated after the yield
        result_attr_out = {
            k: v for k, v in spider.__dict__.items()
            if k not in ('crawler', 'settings', 'start_urls')
        }

        self.assertEqual(data['spider_args_out'], result_attr_out, 'Not equal!'
                         )
    return test
