import os
from glob import glob
from importlib import import_module

from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.utils.reqser import request_from_dict
from scrapy.utils.project import get_project_settings
from scrapy.utils.misc import load_object, arg_to_iter

from testfixtures import compare

from .parser import Parser
from .cassette import Cassette
from .utils import get_spider_class, python_version


class Player(Parser):
    def __init__(self, fixtures_dir):
        pattern = os.path.join(fixtures_dir, "*.bin")
        self.fixtures = glob(pattern)

    def _auto_import(self, qualified_name):
        mod_name, class_name = qualified_name.rsplit('.', 1)
        return getattr(import_module(mod_name), class_name)

    def _create_instance(self, objcls, settings, crawler, *args, **kwargs):
        if settings is None:
            if crawler is None:
                raise ValueError(
                    "Specifiy at least one of settings and crawler.")
            settings = crawler.settings
        if crawler and hasattr(objcls, 'from_crawler'):
            return objcls.from_crawler(crawler, *args, **kwargs)
        elif hasattr(objcls, 'from_settings'):
            return objcls.from_settings(settings, *args, **kwargs)
        else:
            return objcls(*args, **kwargs)

    def _clean(self, x, y, fields):
        for obj in (x, y):
            for field in fields:
                obj.pop(field, None)

    def _check_python_version(self):
        current = python_version()
        recorded = self.cassette.python_version
        assert current == recorded, (
            'Trying to test python {} fixture '
            'while running python {}'.format(recorded, current)
        )

    def _create_spider(self):
        settings = get_project_settings()
        spider_cls = get_spider_class(
            self.cassette.spider_name, settings)

        spider_cls.update_settings(settings)
        for k, v in self.cassette.included_settings.items():
            settings.set(k, v, priority=50)

        crawler = Crawler(spider_cls, settings)
        spider = spider_cls.from_crawler(
            crawler, **self.cassette.init_attrs)
        crawler.spider = spider

        self.spider = spider
        self.crawler = crawler

        spider.start_requests()
        crawler.signals.send_catch_log(
            signal=signals.spider_opened,
            spider=spider)

    def _compare(self, expected, found, message):
        x_label = "expected"
        y_label = "found"
        compare(
            expected=expected,
            actual=found,
            x_label=x_label,
            y_label=y_label,
            prefix=message,
        )

    def _compare_items(self, index, found, expected):
        # Get recorded data and parse callback's output
        expected_type = expected['type']
        expected_data = expected['data']
        found_data = self.parse_object(found)

        # Clean both objects using the skipped fields from settings
        setting_name = 'AUTOUNIT_SKIPPED_FIELDS'
        if expected_type == 'request':
            setting_name = 'AUTOUNIT_REQUEST_SKIPPED_FIELDS'
        to_clean = self.spider.settings.get(setting_name, default=[])
        self._clean(expected_data, found_data, to_clean)

        self._compare(
            expected=expected_data,
            found=found_data,
            message=(
                "Callback output #{} doesn't "
                "match recorded output".format(index)
            )
        )

    def len(self, iterator):
        return len(list(iterator)) + 1

    def _compare_outputs(self, found, expected):
        sentinel = object()

        # Iterate the callback output comparing it with the recorded output
        for index, found_item in enumerate(found, start=1):
            expected_item = next(expected, sentinel)
            if expected_item == sentinel:
                raise AssertionError(
                    "Callback returned {} more item/s than expected".format(
                        self.len(found)))
            self._compare_items(index, found_item, expected_item)

        # Check if we expected more data than the found
        expected_more = next(expected, sentinel)
        if expected_more != sentinel:
            raise AssertionError(
                "Expected {} more item/s from callback".format(
                    self.len(expected)))

    def _playback_cassette(self):
        # Compare attributes set by spider's init
        self._compare(
            expected=self.cassette.init_attrs,
            found=self.get_spider_attrs(),
            message="Init attributes not equal"
        )

        # Set spider attributes as they were before the callback
        for k, v in self.cassette.input_attrs.items():
            setattr(self.spider, k, v)

        # Create Request and Response objects
        request = request_from_dict(self.cassette.request, self.spider)
        response_cls = self._auto_import(self.cassette.response.pop(
            'cls', 'scrapy.http.HtmlResponse'))
        response = response_cls(request=request, **self.cassette.response)

        # Create middlewares instances
        middlewares = []
        for mw_path in self.cassette.middlewares:
            try:
                mw_cls = load_object(mw_path)
                mw = self._create_instance(
                    mw_cls, self.spider.settings, self.crawler)
                middlewares.append(mw)
            except NotConfigured:
                continue

        # Compare spider attributes before the callback
        self._compare(
            expected=self.cassette.input_attrs,
            found=self.get_spider_attrs(),
            message="Input arguments not equal"
        )

        # Run middlewares process_spider_input methods
        for mw in middlewares:
            if hasattr(mw, 'process_spider_input'):
                mw.process_spider_input(response, self.spider)

        # Run the callback
        cb_kwargs = getattr(request, "cb_kwargs", {})
        output = arg_to_iter(request.callback(response, **cb_kwargs))

        # Run middlewares process_spider_output methods
        middlewares.reverse()
        for mw in middlewares:
            if hasattr(mw, 'process_spider_output'):
                output = mw.process_spider_output(
                    response, output, self.spider)

        # Compare callback output (found) with recorded output (expected)
        found = iter(output)
        expected = iter(self.cassette.output_data)
        self._compare_outputs(found, expected)

        # Compare spider attributes after callback
        self._compare(
            expected=self.cassette.output_attrs,
            found=self.get_spider_attrs(),
            message="Output arguments not equal"
        )

    def _test_fixture(self, path):
        cassette = Cassette.from_fixture(path)
        self.cassette = cassette
        self._check_python_version()
        self._create_spider()
        self._playback_cassette()

    def playback(self):
        for path in self.fixtures:
            self._test_fixture(path)
            break
