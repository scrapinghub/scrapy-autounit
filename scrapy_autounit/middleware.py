import os
import six
import pickle
import random
import logging

from scrapy.exceptions import NotConfigured
from scrapy.commands.genspider import sanitize_module_name

from .utils import (
    add_sample,
    write_test,
    response_to_dict,
    get_or_create_test_dir,
    parse_request,
    get_project_dir,
    get_middlewares,
    create_dir,
    parse_callback_result,
    clear_fixtures,
    get_filter_attrs,
)

logger = logging.getLogger(__name__)


def _copy_settings(settings):
    out = {}
    for name in settings.getlist('AUTOUNIT_INCLUDED_SETTINGS', []):
        out[name] = settings.get(name)
    return out


class AutounitMiddleware:
    def __init__(self, crawler):
        settings = crawler.settings
        spider = crawler.spider

        if not any(
            self.__class__.__name__ in s
            for s in settings.getwithbase('SPIDER_MIDDLEWARES').keys()
        ):
            raise ValueError(
                '%s must be in SPIDER_MIDDLEWARES' % (
                    self.__class__.__name__,))
        if not settings.getbool('AUTOUNIT_ENABLED'):
            raise NotConfigured('scrapy-autounit is not enabled')
        if settings.getint('CONCURRENT_REQUESTS') > 1:
            logger.warn(
                'Recording with concurrency > 1! '
                'Data races in shared object modification may create broken '
                'tests.'
            )

        self.max_fixtures = settings.getint(
            'AUTOUNIT_MAX_FIXTURES_PER_CALLBACK',
            default=10
        )
        self.max_fixtures = \
            self.max_fixtures if self.max_fixtures >= 10 else 10

        self.base_path = settings.get(
            'AUTOUNIT_BASE_PATH',
            default=os.path.join(get_project_dir(), 'autounit')
        )
        create_dir(self.base_path, exist_ok=True)
        clear_fixtures(self.base_path, sanitize_module_name(spider.name))

        self.fixture_counters = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_spider_input(self, response, spider):
        response.meta['_autounit'] = pickle.dumps({
            'request': parse_request(response.request, spider),
            'response': response_to_dict(response),
            'spider_args': {
                k: v for k, v in spider.__dict__.items()
                if k not in get_filter_attrs(spider)
            },
            'middlewares': get_middlewares(spider),
        })
        return None

    def process_spider_output(self, response, result, spider):
        settings = spider.settings

        processed_result, out = parse_callback_result(result, spider)

        input_data = pickle.loads(response.meta.pop('_autounit'))

        request = input_data['request']
        callback_name = request['callback']
        spider_attr_out = {
            k: v for k, v in spider.__dict__.items()
            if k not in get_filter_attrs(spider)
        }

        data = {
            'spider_name': spider.name,
            'request': request,
            'response': input_data['response'],
            'spider_args_out': spider_attr_out,
            'result': processed_result,
            'spider_args_in': input_data['spider_args'],
            'settings': _copy_settings(settings),
            'middlewares': input_data['middlewares'],
            'python_version': 2 if six.PY2 else 3,
        }

        callback_counter = self.fixture_counters.setdefault(callback_name, 0)
        self.fixture_counters[callback_name] += 1

        test_dir, test_name = get_or_create_test_dir(
            self.base_path,
            sanitize_module_name(spider.name),
            callback_name,
            settings.get('AUTOUNIT_EXTRA_PATH'),
        )

        index = 0
        if callback_counter < self.max_fixtures:
            index = callback_counter + 1
            add_sample(index, test_dir, test_name, data)
        else:
            r = random.randint(0, callback_counter)
            if r < self.max_fixtures:
                index = r + 1
                add_sample(index, test_dir, test_name, data)

        if index == 1:
            write_test(test_dir, test_name, request['url'])

        return out
