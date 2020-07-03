from importlib import import_module

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.reqser import request_from_dict
from scrapy.utils.misc import load_object, arg_to_iter

from testfixtures import compare

from .parser import Parser
from .cassette import Cassette
from .utils import python_version


class Player(Parser):
    def __init__(self, cassette):
        self.cassette = cassette

    @classmethod
    def from_fixture(cls, path):
        cassette = Cassette.from_fixture(path)
        player = Player(cassette)
        return player

    def _len(self, iterator):
        return len(list(iterator)) + 1

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

    def _init_spider(self):
        spider = self.cassette.get_spider()
        spider.start_requests()
        spider.crawler.signals.send_catch_log(
            signal=signals.spider_opened,
            spider=spider)
        self.spider = spider
        self.crawler = spider.crawler

    def _http_objects(self):
        request = request_from_dict(self.cassette.request, self.spider)
        response_cls = self._auto_import(self.cassette.response.pop(
            'cls', 'scrapy.http.HtmlResponse'))
        response = response_cls(request=request, **self.cassette.response)
        return request, response

    def _get_middlewares(self):
        middlewares = []
        for mw_path in self.cassette.middlewares:
            try:
                mw_cls = load_object(mw_path)
                mw = self._create_instance(
                    mw_cls, self.spider.settings, self.crawler)
                middlewares.append(mw)
            except NotConfigured:
                continue
        return middlewares

    def _compare(self, expected, found, message):
        x_label = "expected"
        y_label = "found"
        compare(
            expected=expected,
            actual=found,
            x_label=x_label,
            y_label=y_label,
            prefix="{} ({})".format(message, self.cassette.filename),
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

    def _compare_outputs(self, found, expected):
        sentinel = object()

        # Iterate the callback output comparing it with the recorded output
        for index, found_item in enumerate(found, start=1):
            expected_item = next(expected, sentinel)
            if expected_item == sentinel:
                raise AssertionError(
                    "Callback returned {} more item/s "
                    "than expected ({})".format(
                        self._len(found), self.cassette.filename))
            self._compare_items(index, found_item, expected_item)

        # Check if we expected more data than the found
        expected_more = next(expected, sentinel)
        if expected_more != sentinel:
            raise AssertionError(
                "Expected {} more item/s from callback ({})".format(
                    self._len(expected), self.cassette.filename))

    def _compare_attrs(self, attrs):
        # Compare attributes set by spider's init
        self._compare(
            expected=self.cassette.init_attrs,
            found=attrs['init'],
            message="Init attributes not equal"
        )

        # Compare spider attributes before the callback
        self._compare(
            expected=self.cassette.input_attrs,
            found=attrs['input'],
            message="Input arguments not equal"
        )

        # Compare spider attributes after callback
        self._compare(
            expected=self.cassette.output_attrs,
            found=attrs['output'],
            message="Output arguments not equal"
        )

    def playback(self, compare=True):
        self._check_python_version()
        self._init_spider()

        attrs = {}
        attrs['init'] = self.get_spider_attrs()

        # Set spider attributes as they were before the callback
        for k, v in self.cassette.input_attrs.items():
            setattr(self.spider, k, v)

        attrs['input'] = self.get_spider_attrs()

        # Create Request and Response objects
        request, response = self._http_objects()

        # Create middlewares instances
        middlewares = self._get_middlewares()

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

        found = iter(output)
        expected = iter(self.cassette.output_data)

        if compare:
            self._compare_outputs(found, expected)
            attrs['output'] = self.get_spider_attrs()
            self._compare_attrs(attrs)
        else:
            # Just exhaust the callback output so we can get output attributes
            for _ in found:
                pass
            attrs['output'] = self.get_spider_attrs()

        return output, attrs
