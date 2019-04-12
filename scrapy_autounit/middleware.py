import random
from pathlib import Path

from scrapy.http import Request
from scrapy.exceptions import NotConfigured

from .utils import (
    add_sample,
    response_to_dict,
    get_or_create_fixtures_dir,
    parse_request,
    parse_object,
    get_project_dir,
)


def _copy_settings(settings):
    out = {}
    for name in settings.getlist('AUTOUNIT_INCLUDED_SETTINGS', []):
        out[name] = settings.get(name)
    return out


class AutounitMiddleware:
    def __init__(self, settings):
        if not settings.getbool('AUTOUNIT_ENABLED'):
            raise NotConfigured('scrapy-autounit is not enabled')

        settings = settings

        self.max_fixtures = settings.getint(
            'AUTOUNIT_MAX_FIXTURES_PER_CALLBACK',
            default=10
        )
        self.max_fixtures = \
            self.max_fixtures if self.max_fixtures >= 10 else 10

        self.base_path = Path(settings.get(
            'AUTOUNIT_BASE_PATH',
            default=get_project_dir() / 'autounit'
        ))
        Path.mkdir(self.base_path, exist_ok=True)

        self.fixture_counters = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_spider_input(self, response, spider):
        response.meta['_autounit'] = {
            'request': parse_request(response.request, spider),
            'response': response_to_dict(response),
            'spider_args': {
                k: v for k, v in spider.__dict__.items()
                if k not in ('crawler', 'settings', 'start_urls')
            }
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
                'data': parse_object(elem, spider)
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

        if callback_counter < self.max_fixtures:
            add_sample(callback_counter + 1, fixtures_dir, data)
        else:
            r = random.randint(0, callback_counter)
            if r < self.max_fixtures:
                add_sample(r + 1, fixtures_dir, data)

        return out
