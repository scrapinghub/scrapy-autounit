import json
import scrapy
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


def get_autounit_base_path():
    settings = get_project_settings()
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


def response_to_dict(response):
    return {
        'url': response.url,
        'status': response.status,
        'body': response.body.decode('utf-8', 'replace'),
        'headers': parse_headers(response.headers),
        'flags': response.flags
    }


def get_spider_class(spider_name):
    project_settings = get_project_settings()
    spider_modules = project_settings.get('SPIDER_MODULES')

    for spider_module in spider_modules:
        modules = walk_modules(spider_module)
        for module in islice(modules, 1, None):
            for spider_class in iter_spider_classes(module):
                if spider_class.name == spider_name:
                    return spider_class
    return None


def parse_result(result, spider):
    parsed_result = []
    for _object in result:
        parsed_result.append({
            'type': 'request' if isinstance(_object, Request) else 'item',
            'data': parse_object(_object, spider=spider)
        })

    return parsed_result


def parse_object(_object, spider=None):
    if isinstance(_object, Request):
        _object = parse_request(_object, spider)
    elif isinstance(_object, Item):
        _object = parse_item(_object)
    return _object


def parse_request(request, spider):
    parsed_request = request_to_dict(request, spider=spider)
    if not parsed_request['callback']:
        parsed_request['callback'] = 'parse'

    parsed_request['headers'] = parse_headers(parsed_request['headers'])
    parsed_request['body'] = parsed_request['body'].decode('utf-8')

    _meta = {}
    for key, value in parsed_request.get('meta').items():
        _meta[key] = parse_object(value)

    parsed_request['meta'] = _meta

    return parsed_request


def parse_headers(headers):
    settings = get_project_settings()
    exclude_headers = settings.get(
        'AUTOUNIT_EXCLUDE_HEADERS',
        default=[]
    )
    auth_headers = ['Authorization', 'Proxy-Authorization']
    parsed_headers = {}
    for key, header in headers.items():
        if isinstance(key, bytes):
            key = key.decode('utf-8')

        if key in auth_headers or key in exclude_headers:
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


def parse_item(item):
    settings = get_project_settings()
    ignored_fields = settings.get(
        'AUTOUNIT_IGNORED_FIELDS',
        default=[]
    )
    if isinstance(item, (Item, dict)):
        _item = {}
        for key, value in item.items():
            if key in ignored_fields: continue
            _item[key] = parse_item(value)
        return _item

    if isinstance(item, (tuple, list)):
        return [parse_item(value) for value in item]

    return item


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
    def test_{spider_name}_{callback_name}_{fixture_name}(self):
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
'''.format(fixture_name=fixture_name, spider_name=spider_path.name,
        callback_name=callback_path.name)

    with open(test_path, 'w') as f:
        f.write(test_code)


def test_generator(fixture_path):
    callback_name = fixture_path.parent.name
    spider_name = fixture_path.parent.parent.name

    spider_cls = get_spider_class(spider_name)
    spider = spider_cls()
    callback = getattr(spider, callback_name, None)

    def test(self):
        with open(fixture_path) as f:
            data = json.load(f)
        fixture_objects = data['result']

        data['request'].pop('_encoding', None)
        data['request'].pop('callback', None)

        request = Request(callback=callback, **data['request'])
        response = HtmlResponse(encoding='utf-8',
            request=request, **data['response'])

        callback_response = list(callback(response))
        for index, _object in enumerate(callback_response):
            fixture_data = fixture_objects[index]['data']
            _object = parse_object(_object, spider=spider)
            self.assertEqual(fixture_data, _object, 'Not equal!')
    return test
