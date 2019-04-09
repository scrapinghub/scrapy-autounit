import random
from pathlib import Path

from scrapy.http import Request
from scrapy.exceptions import NotConfigured

from .utils import (
    add_file,
    response_to_dict,
    get_or_create_fixtures_dir,
    parse_request,
    parse_object,
    get_autounit_base_path,
    write_test,
    get_spider_args,
)


def _copy_settings(settings):
    out = {}
    print(settings.attributes.keys())
    for name in settings.getlist('AUTOUNIT_INCLUDED_SETTINGS', []):
        out[name] = settings.get(name)
    return out


class AutounitMiddleware:
    def __init__(self, settings):
        if not settings.getbool('AUTOUNIT_ENABLED'):
            raise NotConfigured('scrapy-autounit is not enabled')

        self.max_fixtures = settings.getint(
            'AUTOUNIT_MAX_FIXTURES_PER_CALLBACK',
            default=10
        )
        self.max_fixtures = \
            self.max_fixtures if self.max_fixtures >= 10 else 10

        self.base_path = get_autounit_base_path()
        Path.mkdir(self.base_path, exist_ok=True)

        self.fixture_counters = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def add_sample(self, index, fixtures_dir, data, compress):
        filename = 'fixture%s.json' % str(index)
        path = fixtures_dir / filename
        add_file(data, path, compress)
        write_test(path)

    def process_spider_input(self, response, spider):
        settings = spider.settings
        response.meta['_autounit'] = {
            'request': parse_request(response.request, spider, settings),
            'response': response_to_dict(response, spider, settings),
            'spider_args': get_spider_args(spider)
        }
        return None

    def process_spider_output(self, response, result, spider):
        settings = spider.settings

        processed_result = []
        out = []

        for elem in result:
            out.append(elem)
            processed_result.append({
                'type': 'request' if isinstance(elem, Request) else 'item',
                'data': parse_object(elem, spider, settings=settings)
            })

        input_data = response.meta.pop('_autounit')
        request = input_data['request']
        callback_name = request['callback']

        data = {
            'request': request,
            'response': input_data['response'],
            'result': processed_result,
            'spider_args': input_data['spider_args'],
            'settings': _copy_settings(settings),
        }

        callback_counter = self.fixture_counters.setdefault(callback_name, 0)
        self.fixture_counters[callback_name] += 1

        fixtures_dir = get_or_create_fixtures_dir(
            self.base_path,
            spider.name,
            callback_name
        )

        compress = settings.getbool('AUTOUNIT_COMPRESS')

        if callback_counter < self.max_fixtures:
            self.add_sample(callback_counter + 1, fixtures_dir, data, compress)
        else:
            r = random.randint(0, callback_counter)
            if r < self.max_fixtures:
                self.add_sample(r + 1, fixtures_dir, data, compress)

        return out
