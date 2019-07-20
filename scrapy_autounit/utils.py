import re
import os
import zlib
import pickle
from pathlib import Path
from itertools import islice
from importlib import import_module

from scrapy import signals
from scrapy.item import Item
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse, Request
from scrapy.utils.reqser import request_to_dict, request_from_dict
from scrapy.utils.spider import iter_spider_classes
from scrapy.utils.project import get_project_settings
from scrapy.utils.misc import walk_modules, load_object, create_instance
from scrapy.utils.conf import (
    init_env,
    closest_scrapy_cfg,
    build_component_list,
)

import pdb

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
    # mw_paths = [mw for mw in full_list if mw != autounit_mw_path]
    # mw_paths = full_list
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
    fixture_name = 'fixture%s' % str(index)
    filename = fixture_name + '.bin'
    path = test_dir / filename
    data = compress_data(pickle_data(data))
    with open(str(path), 'wb') as outfile:
        outfile.write(data)
    write_test(test_dir, test_name, fixture_name)


def compress_data(data):
    return zlib.compress(data)


def decompress_data(data):
    return zlib.decompress(data)


def pickle_data(data):
    return pickle.dumps(data, protocol=2)


def unpickle_data(data):
    return pickle.loads(data)


def response_to_dict(response):
    return {
        'url': response.url,
        'status': response.status,
        'body': response.body,
        'headers': response.headers,
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

    if isinstance(_object, (dict, Item)):
        _object = _object.copy()
        clean_item(_object, spider.settings)

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

    clean_request(_request, spider.settings)

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
    _clean(item, settings, 'AUTOUNIT_EXCLUDED_FIELDS')
    _clean(item, settings, 'AUTOUNIT_SKIPPED_FIELDS')


def _clean(data, settings, name):
    fields = settings.get(name, default=[])
    for field in fields:
        data.pop(field, None)


def get_valid_identifier(name):
    return re.sub('[^0-9a-zA-Z_]', '_', name.strip())


def _clean_attr(spider_attr, _exclude_attr):
    _re_exclude_attr = re.compile(r'|'.join(_exclude_attr))
    _spider_attr = {k: v for k, v in spider_attr.items()
                    if (k not in ['settings', 'crawler']
                        and not _re_exclude_attr.findall(k))}
    return _spider_attr


def write_test(path, test_name, fixture_name):
    test_path = path / ('test_%s.py' % (fixture_name))

    test_code = '''import unittest
from pathlib import Path
from scrapy_autounit.utils import test_generator


class AutoUnit(unittest.TestCase):
    def test__{test_name}__{fixture_name}(self):
        self.maxDiff = None
        file_path = (
            Path(__file__).parent / '{fixture_name}.bin'
        )
        test = test_generator(file_path.resolve())
        test(self)


if __name__ == '__main__':
    unittest.main()
'''.format(
        test_name=test_name,
        fixture_name=fixture_name,
    )

    with open(str(test_path), 'w') as f:
        f.write(test_code)


def set_spider_attrs(spider, _args):
    for k, v in _args.items():
        setattr(spider, k, v)
    return spider

def test_generator(fixture_path):
    global spider
    with open(str(fixture_path), 'rb') as f:
        data = f.read()

    data = unpickle_data(decompress_data(data))

    spider_name = data.get('spider_name')
    if not spider_name:  # legacy tests
        spider_name = fixture_path.parent.parent.name

    settings = get_project_settings()

    spider_cls = get_spider_class(spider_name, settings)
    spider_cls.update_settings(settings)
    for k, v in data.get('settings', {}).items():
        settings.set(k, v, 50)
    spider = spider_cls(**data.get('spider_args'))
    spider.settings = settings
    # print(data.get('spider_args_out'))
    # for k, v in data.get('spider_args').items():
    #     setattr(spider, k, v)
    crawler = Crawler(spider_cls, settings)

    def test(self):
        global spider
        fixture_objects = data['result']
        # print(data)
        
        spider = set_spider_attrs(spider, data['spider_args'])

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
            middlewares.append(mw)
        print("Middleware:", middleware_paths)

        crawler.signals.send_catch_log(
            signal=signals.spider_opened,
            spider=spider
        )

        print('!' * 30 )
        print(response.__dict__)
        print(response.request.__dict__)
        for mw in middlewares:
            if hasattr(mw, 'process_spider_input'):
                mw.process_spider_input(response, spider)

        result = request.callback(response) or []
        print([r for r in result])
        middlewares.reverse()

        # self.set_spider_attrs(spider, data.get('spider_args_out'))
        print('oooooo')
        for mw in middlewares:
            if hasattr(mw, 'process_spider_output'):
                result = mw.process_spider_output(response, result, spider)

        crawler.signals.send_catch_log(
           signal=signals.spider_closed,
           spider=spider
        )
        if isinstance(result, (Item, Request, dict)):
            result = [result]

        print('*!' * 25)
        print(request.__dict__)
        print(spider.__dict__)
        print(data['spider_args'])
        print(data['spider_args_in'])
        print(data['spider_args_out'])
        # for l in data['traceback_out'].format():
        #     print(l)
        #     print('\n' * 2)
        print('*' * 25)
        result_attr ={
                k: v for k, v in spider.__dict__.items()
                if k not in ('crawler', 'settings', 'start_urls')
            }
        for index, _object in enumerate(result):
            fixture_data = fixture_objects[index]['data']

            if fixture_objects[index].get('type') == 'request':
                clean_request(fixture_data, settings)
            else:
                clean_item(fixture_data, settings)
            self.assertEqual(_object, '', 'Object')
            _object = parse_object(_object, spider)

            #self.assertNotEqual(fixture_data, _object, 'Are equal!')
            self.assertEqual(fixture_data, _object, 'Not equal!')

        #import pandas as pd
        #print(pd.concat([pd.Series(result_attr).rename('result'), pd.Series(fixture_attr).rename('test_result')],axis=1))
        self.assertEqual(data['spider_args_out'], result_attr, 'Not equal!')
        print(data['spider_args_out'], result_attr)
    return test
