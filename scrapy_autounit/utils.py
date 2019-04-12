import re
import os
import zlib
import pickle
from pathlib import Path
from itertools import islice
from importlib import import_module
from base64 import b64encode, b64decode

from scrapy.item import Item
from scrapy.http import HtmlResponse, Request
from scrapy.utils.reqser import request_to_dict
from scrapy.utils.misc import walk_modules
from scrapy.utils.spider import iter_spider_classes
from scrapy.utils.project import get_project_settings
from scrapy.utils.conf import init_env, closest_scrapy_cfg


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


def get_or_create_fixtures_dir(base_path, spider_name, callback_name):
    create_tests_tree(base_path, spider_name, callback_name)
    fixtures_dir = base_path / 'fixtures' / spider_name / callback_name
    Path.mkdir(fixtures_dir, parents=True, exist_ok=True)
    return fixtures_dir


def create_tests_tree(base_path, spider_name, callback_name):
    tests_dir = base_path / 'tests' / spider_name / callback_name
    Path.mkdir(tests_dir, parents=True, exist_ok=True)
    (base_path / '__init__.py').touch()
    (base_path / 'tests' / '__init__.py').touch()
    (base_path / 'tests' / spider_name / '__init__.py').touch()
    (base_path / 'tests' / spider_name / callback_name / '__init__.py').touch()


def add_sample(index, fixtures_dir, data):
    filename = 'fixture%s.txt' % str(index)
    path = fixtures_dir / filename
    data = compress_data(pickle_data(data))
    with open(path, 'w') as outfile:
        outfile.write(data.decode('utf-8'))
    write_test(path)


def compress_data(data):
    return b64encode(zlib.compress(data, level=9))


def decompress_data(data):
    return zlib.decompress(b64decode(data))


def pickle_data(data):
    return b64encode(pickle.dumps(data))


def unpickle_data(data):
    return pickle.loads(b64decode(data))


def response_to_dict(response):
    return {
        'url': response.url,
        'status': response.status,
        'body': response.body.decode('utf-8', 'replace'),
        'headers': response.headers,
        'flags': response.flags
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
    _request['body'] = _request['body'].decode('utf-8')

    _meta = {}
    for key, value in _request.get('meta').items():
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


def write_test(fixture_path):
    fixture_name = fixture_path.stem
    callback_path = fixture_path.parent
    spider_path = callback_path.parent
    base_path = spider_path.parent.parent

    test_path = (
        base_path / 'tests' / spider_path.name /
        callback_path.name / f'test_{fixture_name}.py'
    )

    test_code = '''import unittest
from pathlib import Path
from scrapy_autounit.utils import test_generator


class AutoUnit(unittest.TestCase):
    def test_{fn_spider_name}_{callback_name}_{fixture_name}(self):
        self.maxDiff = None
        file_path = (
            Path(__file__) /
            '../../../../fixtures' /
            '{spider_name}' /
            '{callback_name}' /
            '{fixture_name}.txt'
        )
        test = test_generator(file_path.resolve())
        test(self)


if __name__ == '__main__':
    unittest.main()
'''.format(
        fixture_name=fixture_name,
        fn_spider_name=get_valid_identifier(spider_path.name),
        spider_name=spider_path.name,
        callback_name=callback_path.name
    )

    with open(test_path, 'w') as f:
        f.write(test_code)


def test_generator(fixture_path):
    with open(fixture_path, 'r') as f:
        data = f.read()

    data = unpickle_data(decompress_data(data))

    callback_name = fixture_path.parent.name
    spider_name = fixture_path.parent.parent.name

    settings = get_project_settings()

    spider_cls = get_spider_class(spider_name, settings)
    spider_cls.update_settings(settings)
    for k, v in data.get('settings', {}).items():
        settings.set(k, v, 50)
    spider = spider_cls(**data.get('spider_args'))
    spider.settings = settings
    callback = getattr(spider, callback_name, None)

    def test(self):
        fixture_objects = data['result']

        data['request'].pop('_class', None)
        data['request'].pop('_encoding', None)
        data['request'].pop('callback', None)

        request = Request(callback=callback, **data['request'])
        response = HtmlResponse(
            encoding='utf-8',
            request=request,
            **data['response']
        )

        callback_response = callback(response)
        if isinstance(callback_response, (Item, Request, dict)):
            callback_response = [callback_response]

        for index, _object in enumerate(callback_response):
            fixture_data = fixture_objects[index]['data']
            if fixture_objects[index].get('type') == 'request':
                clean_request(fixture_data, settings)
            else:
                clean_item(fixture_data, settings)

            _object = parse_object(_object, spider)
            self.assertEqual(fixture_data, _object, 'Not equal!')

    return test
