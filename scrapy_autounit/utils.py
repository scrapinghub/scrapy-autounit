import re
import json
import types
import os
from pathlib import Path
from itertools import islice
from importlib import import_module

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
    except ImportError as exc:
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
    with open(path, 'w') as outfile:
        json.dump(data, outfile, sort_keys=True, indent=2)


def response_to_dict(response, spider):
    return {
        'url': response.url,
        'status': response.status,
        'body': response.body.decode('utf-8', 'replace'),
        'headers': parse_headers(response.headers, spider),
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


def parse_object(_object, spider=None, testing=False, already_parsed=False):
    if isinstance(_object, Request):
        return parse_request(_object, spider,
            testing=testing, already_parsed=already_parsed)
    return parse_item(_object, spider, testing=testing)


def parse_request(request, spider, testing=False, already_parsed=False):
    parsed_request = request
    if not already_parsed:
        parsed_request = request_to_dict(request, spider=spider)
        if not parsed_request['callback']:
            parsed_request['callback'] = 'parse'

        parsed_request['headers'] = parse_headers(
            parsed_request['headers'], spider)

        parsed_request['body'] = parsed_request['body'].decode('utf-8')

        _meta = {}
        for key, value in parsed_request.get('meta').items():
            _meta[key] = parse_object(value, spider,
                testing=testing, already_parsed=already_parsed)

        parsed_request['meta'] = _meta

    settings = get_settings(spider=spider)
    skipped_fields = settings.get(
        'AUTOUNIT_REQUEST_SKIPPED_FIELDS', default=[])
    if testing:
        for field in skipped_fields:
            parsed_request.pop(field)

    return parsed_request


def parse_headers(headers, spider):
    settings = get_settings(spider=spider)
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


def parse_item(item, spider, testing=False):
    settings = get_settings(spider=spider)
    excluded_fields = settings.get('AUTOUNIT_EXCLUDED_FIELDS', default=[])
    skipped_fields = settings.get('AUTOUNIT_SKIPPED_FIELDS', default=[])
    if isinstance(item, (Item, dict)):
        _item = {}
        for key, value in item.items():
            if key in excluded_fields: continue
            if testing and key in skipped_fields: continue
            _item[key] = parse_item(value, spider, testing=testing)
        return _item

    if isinstance(item, (tuple, list)):
        return [parse_item(value, spider, testing=testing) for value in item]

    return item


def get_valid_identifier(name):
    return re.sub('[^0-9a-zA-Z_]', '_', name.strip())


def get_spider_args(spider):
    return {k: v for k, v in spider.__dict__.items()
        if k not in ('crawler', 'settings', 'start_urls')}


def write_test(fixture_path):
    fixture_name = fixture_path.stem
    callback_path = fixture_path.parent
    spider_path = callback_path.parent
    base_path = spider_path.parent.parent

    test_path = (base_path / 'tests' / spider_path.name /
        callback_path.name / f'test_{fixture_name}.py')

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

    callback_name = fixture_path.parent.name
    spider_name = fixture_path.parent.parent.name

    spider_cls = get_spider_class(spider_name)
    spider = spider_cls(**data.get('spider_args'))
    callback = getattr(spider, callback_name, None)

    def test(self):
        fixture_objects = data['result']

        data['request'].pop('_encoding', None)
        data['request'].pop('callback', None)

        request = Request(callback=callback, **data['request'])
        response = HtmlResponse(encoding='utf-8',
            request=request, **data['response'])

        callback_response = callback(response)
        if isinstance(callback_response, types.GeneratorType):
            callback_response = list(callback_response)
        else:
            callback_response = [callback_response]

        for index, _object in enumerate(callback_response):
            if fixture_objects[index].get('type') == 'request':
                fixture_data = parse_request(
                    fixture_objects[index]['data'],
                    spider,
                    testing=True,
                    already_parsed=True
                )
            else:
                fixture_data = parse_item(
                    fixture_objects[index]['data'], spider, testing=True)

            _object = parse_object(_object, spider=spider, testing=True)
            self.assertEqual(fixture_data, _object, 'Not equal!')

    return test
