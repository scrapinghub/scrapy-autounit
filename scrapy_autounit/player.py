import os
import six
from glob import glob
from importlib import import_module

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.reqser import request_from_dict
from scrapy.utils.misc import load_object, arg_to_iter

from testfixtures import compare

from .cassette import Cassette
from .utils import get_spider_attrs


class Player:
    NO_ITEM_MARKER = object()

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

    def _get_http_objects(self, cassette):
        request = request_from_dict(cassette.request, cassette.spider)
        response_cls = self._auto_import(cassette.response.pop(
            'cls', 'scrapy.http.HtmlResponse'))
        response = response_cls(request=request, **cassette.response)
        return request, response

    def _clean(self, x, y, fields):
        for obj in (x, y):
            for field in fields:
                obj.pop(field, None)

    def _compare(self, expected, actual, message):
        x_label = "recorded"
        y_label = "from callback"
        compare(
            expected=expected,
            actual=actual,
            x_label=x_label,
            y_label=y_label,
            prefix=message,
        )

    def _compare_outputs(self, result, cassette):
        for index, (cb_obj, fx_item) in enumerate(six.moves.zip_longest(
            result, cassette.result, fillvalue=self.NO_ITEM_MARKER
        )):
            if any(item == self.NO_ITEM_MARKER for item in (cb_obj, fx_item)):
                raise AssertionError(
                    "The fixture's data length doesn't match with "
                    "the current callback's output length. "
                    "Expected %s elements, found %s" % (
                        len(cassette.result), index + 1 + len(list(result))
                    )
                )

            cb_obj = cassette.parse_object(cb_obj)
            fx_obj = fx_item['data']

            setting_name = 'AUTOUNIT_SKIPPED_FIELDS'
            if fx_item['type'] == 'request':
                setting_name = 'AUTOUNIT_REQUEST_SKIPPED_FIELDS'
            to_clean = cassette.settings.get(setting_name, default=[])
            self._clean(fx_obj, cb_obj, to_clean)

            # REVIEW
            # if fx_version == 2 and six.PY3:
            #     fx_obj = binary_check(fx_obj, cb_obj, encoding)

            self._compare(
                expected=fx_obj,
                actual=cb_obj,
                message=(
                    "Callback output #{} doesn't "
                    "match recorded output".format(index)
                )
            )
        return None

    def _replay_cassette(self, cassette):
        # Compare attributes set by spider's init
        self._compare(
            expected=cassette.init_attrs,
            actual=get_spider_attrs(cassette.spider),
            message="Init attributes not equal"
        )

        # Set spider attributes as they were before callback
        for k, v in cassette.spider_args_in.items():
            setattr(cassette.spider, k, v)

        # Create Request and Response objects
        request, response = self._get_http_objects(cassette)

        # Create middlewares instances
        middlewares = []
        for mw_path in cassette.middlewares:
            try:
                mw_cls = load_object(mw_path)
                mw = self._create_instance(
                    mw_cls, cassette.settings, cassette.crawler)
                middlewares.append(mw)
            except NotConfigured:
                continue

        # Send open_spider signal
        cassette.crawler.signals.send_catch_log(
            signal=signals.spider_opened,
            spider=cassette.spider
        )

        # Compare spider attributes before the callback
        self._compare(
            expected=cassette.spider_args_in,
            actual=get_spider_attrs(cassette.spider),
            message="Input arguments not equal"
        )

        # Run middlewares process_spider_input methods
        for mw in middlewares:
            if hasattr(mw, 'process_spider_input'):
                mw.process_spider_input(response, cassette.spider)

        # Run the callback
        cb_kwargs = getattr(request, "cb_kwargs", {})
        result = arg_to_iter(request.callback(response, **cb_kwargs))

        # Run middlewares process_spider_output methods
        middlewares.reverse()
        for mw in middlewares:
            if hasattr(mw, 'process_spider_output'):
                result = mw.process_spider_output(
                    response, result, cassette.spider)

        # Compare callback output with recorded output
        self._compare_outputs(result, cassette)

        # Compare spider attributes after callback
        self._compare(
            expected=cassette.spider_args_out,
            actual=get_spider_attrs(cassette.spider),
            message="Output arguments not equal"
        )

    def test(self):
        for path in self.fixtures:
            basename = os.path.basename(path)
            print("Testing fixture '%s'" % (basename))
            cassette = Cassette.from_fixture(path)
            self._replay_cassette(cassette)
