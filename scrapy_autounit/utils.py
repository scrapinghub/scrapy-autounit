import re
import json
import os
import zlib
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


def get_settings(spider=None):
    settings = get_project_settings()
    if spider:
        spider_cls = type(spider)
        settings.setdict(spider_cls.custom_settings)
    return settings


def get_autounit_base_path():
    settings = get_settings()
    return Path(settings.get(
        'AUTOUNIT_BASE_PATH',
        default=get_project_dir() / 'autounit'
    ))


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


def add_file(data, path):
    data['response'] = compress_data(data['response'])
    data['result'] = compress_data(data['result'])
    with open(path, 'w') as outfile:
        json.dump(data, outfile, sort_keys=True, indent=2)


def compress_data(data):
    str_data = json.dumps(data)
    compressed_data = zlib.compress(str_data.encode('utf-8'), level=9)
    return b64encode(compressed_data).decode('utf-8')


def decompress_data(data):
    compressed_data = b64decode(data.encode('utf-8'))
    decompressed_data = zlib.decompress(compressed_data)
    return json.loads(decompressed_data)


def response_to_dict(response, spider, settings):
    return {
        'url': response.url,
        'status': response.status,
        'body': response.body.decode('utf-8', 'replace'),
        'headers': parse_headers(response.headers, spider, settings),
        'flags': response.flags
    }


def get_spider_class(spider_name):
    project_settings = get_settings()
    spider_modules = project_settings.get('SPIDER_MODULES')

    for spider_module in spider_modules:
        modules = walk_modules(spider_module)
        for module in islice(modules, 1, None):
            for spider_class in iter_spider_classes(module):
                if spider_class.name == spider_name:
                    return spider_class
    return None


def parse_object(
    _object,
    spider,
    testing=False,
    already_parsed=False,
    settings=None
):
    if not settings:
        settings = get_settings(spider)

    if isinstance(_object, Request):
        return parse_request(
            _object,
            spider,
            settings,
            testing=testing,
            already_parsed=already_parsed
        )
    return parse_item(
        _object,
        spider,
        settings,
        testing=testing,
        already_parsed=already_parsed
    )


def parse_request(
    request,
    spider,
    settings,
    testing=False,
    already_parsed=False
):
    parsed_request = request
    if not already_parsed:
        parsed_request = request_to_dict(request, spider=spider)
        if not parsed_request['callback']:
            parsed_request['callback'] = 'parse'

        parsed_request['headers'] = parse_headers(
            parsed_request['headers'],
            spider,
            settings
        )

        parsed_request['body'] = parsed_request['body'].decode('utf-8')

        _meta = {}
        for key, value in parsed_request.get('meta').items():
            _meta[key] = parse_object(
                value,
                spider,
                testing=testing,
                already_parsed=already_parsed,
                settings=settings
            )

        parsed_request['meta'] = _meta

    skipped_fields = settings.get(
        'AUTOUNIT_REQUEST_SKIPPED_FIELDS', default=[])
    if testing:
        for field in skipped_fields:
            parsed_request.pop(field)

    return parsed_request


def parse_headers(headers, spider, settings):
    excluded_headers = settings.get('AUTOUNIT_EXCLUDED_HEADERS', default=[])
    auth_headers = ['Authorization', 'Proxy-Authorization']
    parsed_headers = {}
    for key, header in headers.items():
        if isinstance(key, bytes):
            key = key.decode('utf-8')

        if key in auth_headers or key in excluded_headers:
            continue

        if isinstance(header, bytes):
            header = header.decode('utf-8')

        if isinstance(header, list):
            new_list = []
            for item in header:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')
                new_list.append(item)
            header = new_list

        parsed_headers[key] = header

    return parsed_headers


def parse_item(
    item,
    spider,
    settings,
    testing=False,
    already_parsed=False
):
    excluded_fields = settings.get('AUTOUNIT_EXCLUDED_FIELDS', default=[])
    skipped_fields = settings.get('AUTOUNIT_SKIPPED_FIELDS', default=[])

    if isinstance(item, (Item, dict)):
        if already_parsed:
            return {
                k: v for k, v in item.items()
                if k not in skipped_fields and k not in excluded_fields
            }

        _item = {}
        for key, value in item.items():
            if key in excluded_fields or (testing and key in skipped_fields):
                continue
            _item[key] = parse_item(
                value,
                spider,
                settings,
                testing=testing,
                already_parsed=already_parsed
            )
        return _item

    if isinstance(item, (tuple, list)):
        return [parse_item(
            value,
            spider,
            settings,
            testing=testing,
            already_parsed=already_parsed
        ) for value in item]

    return item


def get_valid_identifier(name):
    return re.sub('[^0-9a-zA-Z_]', '_', name.strip())


def get_spider_args(spider):
    return {
        k: v for k, v in spider.__dict__.items()
        if k not in ('crawler', 'settings', 'start_urls')
    }


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
        json_path = (
            Path(__file__) /
            '../../../../fixtures' /
            '{spider_name}' /
            '{callback_name}' /
            '{fixture_name}.json'
        )
        test = test_generator(json_path.resolve())
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
    with open(fixture_path) as f:
        data = json.load(f)

    if not isinstance(data['response'], dict):
        data['response'] = decompress_data(data['response'])
    if not isinstance(data['result'], list):
        data['result'] = decompress_data(data['result'])

    callback_name = fixture_path.parent.name
    spider_name = fixture_path.parent.parent.name

    spider_cls = get_spider_class(spider_name)
    spider = spider_cls(**data.get('spider_args'))
    callback = getattr(spider, callback_name, None)

    def test(self):
        settings = get_settings(spider)
        fixture_objects = data['result']

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
            if fixture_objects[index].get('type') == 'request':
                fixture_data = parse_request(
                    fixture_objects[index]['data'],
                    spider,
                    settings,
                    testing=True,
                    already_parsed=True
                )
            else:
                fixture_data = parse_item(
                    fixture_objects[index]['data'],
                    spider,
                    settings,
                    testing=True,
                    already_parsed=True
                )

            _object = parse_object(
                _object,
                spider,
                testing=True,
                settings=settings
            )
            self.assertEqual(fixture_data, _object, 'Not equal!')

    return test
