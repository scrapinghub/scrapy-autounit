import copy
from scrapy.spiders import CrawlSpider
from scrapy.http import Request, Response
from scrapy.utils.reqser import request_to_dict


class Parser:
    def _clean_headers(self, headers):
        excluded = self.spider.settings.get(
            'AUTOUNIT_EXCLUDED_HEADERS', default=[])
        auth_headers = ['Authorization', 'Proxy-Authorization']
        included = self.spider.settings.get(
            'AUTOUNIT_INCLUDED_AUTH_HEADERS', default=[])
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

    def get_spider_attrs(self):
        filter_attrs = {'crawler', 'settings', 'start_urls'}
        if isinstance(self.spider, CrawlSpider):
            filter_attrs |= {'rules', '_rules'}
        return {
            k: v for k, v in self.spider.__dict__.items()
            if k not in filter_attrs
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
        elif isinstance(_object, (list, tuple)):
            for i, v in enumerate(_object):
                _object[i] = self.parse_object(v)
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
        return (x for x in original), parsed
