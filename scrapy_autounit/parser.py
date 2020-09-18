import copy

from scrapy.http import Request, Response
from scrapy.spiders import CrawlSpider
from scrapy.utils.reqser import request_to_dict


class Parser:
    def _clean_headers(self, headers):
        # Use the new setting, if empty, try the deprecated one
        excluded = self.spider.settings.get('AUTOUNIT_DONT_RECORD_HEADERS', [])
        if not excluded:
            excluded = self.spider.settings.get('AUTOUNIT_EXCLUDED_HEADERS', [])
        auth_headers = ['Authorization', 'Proxy-Authorization']
        # Use the new setting, if empty, try the deprecated one
        included = self.spider.settings.get('AUTOUNIT_RECORD_AUTH_HEADERS', [])
        if not included:
            included = self.spider.settings.get('AUTOUNIT_INCLUDED_AUTH_HEADERS', [])
        excluded.extend([h for h in auth_headers if h not in included])
        for header in excluded:
            headers.pop(header, None)
            headers.pop(header.encode(), None)

    def _request_to_dict(self, request):
        _request = request_to_dict(request, spider=self.spider)
        if not _request['callback']:
            _request['callback'] = 'parse'
        elif isinstance(self.spider, CrawlSpider):
            rule = request.meta.get('rule')
            if rule is not None:
                _request['callback'] = self.spider.rules[rule].callback
        self._clean_headers(_request['headers'])
        _meta = {}
        for key, value in _request.get('meta').items():
            if key != '_autounit_cassette':
                _meta[key] = self.parse_object(value)
        _request['meta'] = _meta
        return _request

    def _response_to_dict(self, response):
        return {
            'cls': '{}.{}'.format(
                type(response).__module__,
                getattr(type(response), '__qualname__', None) or
                getattr(type(response), '__name__', None)
            ),
            'url': response.url,
            'status': response.status,
            'body': response.body,
            'headers': dict(response.headers),
            'flags': response.flags,
            'encoding': response.encoding,
        }

    def spider_attrs(self):
        to_filter = {'crawler', 'settings', 'start_urls'}

        if isinstance(self.spider, CrawlSpider):
            to_filter |= {'rules', '_rules'}

        dont_record_attrs = set(
            self.spider.settings.get('AUTOUNIT_DONT_RECORD_SPIDER_ATTRS', []))
        to_filter |= dont_record_attrs

        return {
            k: v for k, v in self.spider.__dict__.items()
            if k not in to_filter
        }

    def parse_response(self, response_obj):
        request = self._request_to_dict(response_obj.request)
        response = self._response_to_dict(response_obj)
        return request, response

    def parse_object(self, _object):
        if isinstance(_object, Request):
            return self._request_to_dict(_object)
        elif isinstance(_object, Response):
            return self.parse_object(self._response_to_dict(_object))
        elif isinstance(_object, dict):
            for k, v in _object.items():
                _object[k] = self.parse_object(v)
        elif isinstance(_object, list):
            for i, v in enumerate(_object):
                _object[i] = self.parse_object(v)
        elif isinstance(_object, tuple):
            _object = tuple([self.parse_object(o) for o in _object])
        return _object

    def parse_callback_output(self, output):
        parsed = []
        original = []
        for elem in output:
            original.append(elem)
            is_request = isinstance(elem, Request)
            if is_request:
                data = self._request_to_dict(elem)
            else:
                data = self.parse_object(copy.deepcopy(elem))
            parsed.append({
                'type': 'request' if is_request else 'item',
                'data': data
            })
        return iter(original), parsed

    def deprecated_settings(self):
        mapping = {
            'AUTOUNIT_SKIPPED_FIELDS': 'AUTOUNIT_DONT_TEST_OUTPUT_FIELDS',
            'AUTOUNIT_REQUEST_SKIPPED_FIELDS': 'AUTOUNIT_DONT_TEST_REQUEST_ATTRS',
            'AUTOUNIT_EXCLUDED_HEADERS': 'AUTOUNIT_DONT_RECORD_HEADERS',
            'AUTOUNIT_INCLUDED_AUTH_HEADERS': 'AUTOUNIT_RECORD_AUTH_HEADERS',
            'AUTOUNIT_INCLUDED_SETTINGS': 'AUTOUNIT_RECORD_SETTINGS',
        }
        warnings = []
        for old, new in mapping.items():
            if not self.spider.settings.get(old):
                continue
            warnings.append(
                f"DEPRECATED: '{old}' is going to be "
                f"removed soon. Please use '{new}' instead.")
        return warnings
