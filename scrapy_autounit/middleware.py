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
    get_settings
)


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

    def add_sample(self, index, fixtures_dir, data):
        filename = 'fixture%s.json' % str(index)
        path = fixtures_dir / filename
        add_file(data, path)
        write_test(path)

    def process_spider_output(self, response, result, spider):
        settings = get_settings(spider)

        processed_result = []
        out = []

        for elem in result:
            out.append(elem)
            processed_result.append({
                'type': 'request' if isinstance(elem, Request) else 'item',
                'data': parse_object(elem, spider, settings=settings)
            })

        request = parse_request(response.request, spider, settings)
        callback_name = request['callback']

        data = {
            'request': request,
            'response': response_to_dict(response, spider, settings),
            'result': processed_result,
            'spider_args': get_spider_args(spider)
        }

        callback_counter = self.fixture_counters.setdefault(callback_name, 0)
        self.fixture_counters[callback_name] += 1

        fixtures_dir = get_or_create_fixtures_dir(
            self.base_path,
            spider.name,
            callback_name
        )

        if callback_counter < self.max_fixtures:
            self.add_sample(callback_counter + 1, fixtures_dir, data)
        else:
            r = random.randint(0, callback_counter)
            if r < self.max_fixtures:
                self.add_sample(r + 1, fixtures_dir, data)

        return out
