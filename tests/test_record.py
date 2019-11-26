import unittest
import tempfile
import subprocess
import os
import shutil
import re


SPIDER_TEMPLATE = '''
import scrapy
{imports}


class MySpider(scrapy.Spider):
    name = '{name}'

    custom_settings = dict(
        SPIDER_MIDDLEWARES={{
            'scrapy_autounit.AutounitMiddleware': 950,
        }},
        {custom_settings}
    )

    def __init__(self, *args, **kwargs):
        {init}
        super(MySpider, self).__init__(*args, **kwargs)

    def start_requests(self):
        {start_requests}

    def parse(self, response):
        {parse}

    def second_callback(self, response):
        {second_callback}
'''


def run(*pargs, **kwargs):
    proc = subprocess.Popen(*pargs, **kwargs)
    proc.wait()
    out = {
        'returncode': proc.returncode,
        'stdout': proc.stdout.read(),
        'stderr': proc.stderr.read(),
    }
    proc.stderr.close()
    proc.stdout.close()
    return out


def indent(string):
    return '\n'.join('    ' + s for s in string.splitlines())


def process_error(message, result):
    raise AssertionError(
        '{}\nSTDOUT--\n{}\nSTDERR--\n{}'.format(
            message,
            indent(result['stdout'].decode('utf-8')),
            indent(result['stderr'].decode('utf-8')),
        ))


def check_process(message, result):
    if result['returncode'] == 0:
        return
    process_error(message, result)


def indent_message(text):
    _text = re.sub(r'(\n)(\n*)', r'\n\t', text)
    return re.sub(r'^([\n\t]*)(.*)', r'\t\2', _text)


def print_test_output(result):
    # Print the output of the tests
    print('\n')
    print(indent_message(''.join(result['stdout'].decode())))
    print(indent_message(''.join(result['stderr'].decode())))


def itertree(startpath):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        yield('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            yield('{}{}'.format(subindent, f))


class CaseSpider(object):
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        self.proj_dir = os.path.join(self.dir, 'myproject')
        os.mkdir(self.proj_dir)
        with open(os.path.join(self.proj_dir, '__init__.py'), 'w'):
            pass
        with open(os.path.join(self.proj_dir, 'settings.py'), 'w') as dest:
            dest.write('SPIDER_MODULES = ["myproject"]\n')
        self._start_requests = None
        self._parse = None
        self._spider_name = 'myspider'
        self._imports = ''
        self._custom_settings = ''
        self._second_callback = None
        self.init = None

    @property
    def template(self):
        return SPIDER_TEMPLATE

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        shutil.rmtree(self.dir)

    def imports(self, string):
        self._imports = string

    def custom_settings(self, string):
        self._custom_settings = string

    def name(self, string):
        self._spider_name = string

    def set_init(self, string):
        self.init = string

    def start_requests(self, string):
        self._start_requests = string

    def parse(self, string):
        self._parse = string

    def second_callback(self, string):
        self._second_callback = string

    def _write_spider(self):
        with open(os.path.join(self.proj_dir, 'myspider.py'), 'w') as dest:
            dest.write(self.template.format(
                name=self._spider_name,
                init=self.init,
                start_requests=self._start_requests,
                parse=self._parse,
                imports=self._imports,
                custom_settings=self._custom_settings,
                second_callback=self._second_callback
            ))

    def record(self, args=None, settings=None, record_verbosity=False):
        if self._start_requests is None or self._parse is None:
            raise AssertionError()
        self._write_spider()
        env = os.environ.copy()
        env['PYTHONPATH'] = self.dir  # doesn't work if == cwd
        env['SCRAPY_SETTINGS_MODULE'] = 'myproject.settings'
        command_args = [
            'scrapy', 'crawl', self._spider_name,
            '-s', 'AUTOUNIT_ENABLED=1',
        ]
        for k, v in (args or {}).items():
            command_args.append('-a')
            command_args.append('{}={}'.format(k, v))
        for k, v in (settings or {}).items():
            command_args.append('-s')
            command_args.append('{}={}'.format(k, v))
        result = run(
            command_args,
            env=env,
            cwd=self.dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        check_process('Running spider failed!', result)
        if record_verbosity:
            print_test_output(result)
        if not any(
            any(f.endswith('.py') and f != '__init__.py' for f in files)
            for _, _, files in os.walk(os.path.join(self.dir, 'autounit'))
        ):
            process_error('No autounit tests recorded!', result)

    def test(self, test_verbosity=True):
        if self._start_requests is None or self._parse is None:
            raise AssertionError()
        env = os.environ.copy()
        env['SCRAPY_SETTINGS_MODULE'] = 'myproject.settings'
        result = run(
            [
                'python', '-m', 'unittest', 'discover', '-v'
            ],
            env=env,
            cwd=self.dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        check_process('Unit tests failed!', result)
        err = result['stderr'].decode('utf-8')
        tests_ran = int(re.search('Ran ([0-9]+) test', err).group(1) or '0')
        is_ok = re.findall('OK$', err)
        if test_verbosity:
            print_test_output(result)
        if not is_ok or not tests_ran:
            if not tests_ran:
                raise AssertionError(
                    'No tests run!\nProject dir:\n{}'.format(
                        '\n'.join(itertree(self.dir))
                    ))
            elif not test_verbosity:
                print_test_output(result)


class TestRecording(unittest.TestCase):

    def test_normal(self):
        with CaseSpider() as spider:
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse("""
                yield {'a': 4}
            """)
            spider.record()
            spider.test()

    def test_path_extra(self):
        with CaseSpider() as spider:
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse("""
                yield {'a': 4}
            """)
            spider.record(settings=dict(AUTOUNIT_EXTRA_PATH='abc'))
            spider.test()

    def test_spider_attributes(self):
        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                yield {'a': 4}
            """)
            spider.record()
            spider.test()

        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                yield {'a': 4}
            """)
            spider.record(settings=dict(
                AUTOUNIT_EXCLUDED_FIELDS='_base_url',
                AUTOUNIT_INCLUDED_SETTINGS='AUTOUNIT_EXCLUDED_FIELDS'))
            spider.test()

    def test_spider_attributes_recursive(self):
        # Recursive calls including private variables
        with CaseSpider() as spider:
            spider.start_requests("""
                self.__page = 0
                self.param = 0
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,', callback=self.parse)
            """)
            spider.parse("""
                self.param += 1
                reqs = self.second_callback(response)
                for r in reqs:
                    yield r
            """)
            spider.second_callback("""
                self.__page += 1
                if self.__page > 3:
                    self.end = True
                    yield {'a': 4}
                    return
                for i in range(3):
                    yield {'b': '%s_%s;'%(self.__page, i)}
                yield scrapy.Request('data:,%s;'%(self.__page),
                                      callback=self.parse)
                                         """)
            spider.record()
            spider.test()

        # Recursive calls including private variables using getattr
        with CaseSpider() as spider:
            spider.start_requests("""
                self.param = 0
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,', callback=self.parse)
            """)
            spider.parse("""
                self.param += 1
                reqs = self.second_callback(response)
                for r in reqs:
                    yield r
            """)
            spider.second_callback("""
                self.__page = getattr(self, '_MySpider__page', 0) + 1
                if self.__page > 3:
                    self.end = True
                    yield {'a': 4}
                    return
                for i in range(3):
                    yield {'b': '%s_%s;'%(self.__page, i)}
                yield scrapy.Request('data:,%s;'%(self.__page),
                                      callback=self.parse)
                                         """)
            spider.record()
            spider.test()

        # Recursive calls including private variables using getattr
        with CaseSpider() as spider:
            spider.set_init("""self.page_number = 0""")
            spider.start_requests("""
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.page_number += 1
                yield {
                    'page_number': self.page_number
                }
                if self.page_number < 3:
                    yield scrapy.Request('data:text/plain,', dont_filter=True)
            """)
            spider.record()
            spider.test()

    def test_empty(self):
        with CaseSpider() as spider:
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse('pass')
            spider.record()
            spider.test()

    def test_dotted_name(self):
        with CaseSpider() as spider:
            spider.name('my.spider')
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse('pass')
            spider.record()
            spider.test()

    def test_skipped_fields(self):
        with CaseSpider() as spider:
            spider.imports('import time')
            spider.custom_settings('''
                AUTOUNIT_SKIPPED_FIELDS = ['ts']
            ''')
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse('''
                time.sleep(0.5)
                yield {'a': 4, 'ts': time.time()}
            ''')
            spider.record()
            spider.test()

    def test_request_skipped_fields(self):
        with CaseSpider() as spider:
            spider.imports('import random')
            spider.custom_settings('''
                AUTOUNIT_REQUEST_SKIPPED_FIELDS = ['url']
            ''')
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse('''
                yield {'a': 4}
                if not response.meta.get('done'):
                    yield scrapy.Request(
                        'data:text/plain,%s' % random.random(),
                        meta={'done': True}
                    )
            ''')
            spider.record()
            spider.test()

    def test_nested_request_in_output(self):
        with CaseSpider() as spider:
            spider.start_requests('''
                yield scrapy.Request(
                    'data:text/plain,',
                )
            ''')
            spider.parse('''
                yield {'data': response.request}
            ''')
            spider.record()
            spider.test()

    def test_nested_response_in_output(self):
        with CaseSpider() as spider:
            spider.start_requests('''
                yield scrapy.Request(
                    'data:text/plain,',
                )
            ''')
            spider.parse('''
                yield {'data': response}
            ''')
            spider.record()
            spider.test()

    def test_html_response(self):
        with CaseSpider() as spider:
            spider.start_requests('''
                yield scrapy.Request(
                    'data:text/html,'
                    '<div><link><p>text</p></link></div>'
                )
            ''')
            spider.parse('''
                yield {
                    'v': response.css('div > p::text').extract_first()
                }
            ''')
            spider.record()
            spider.test()

    def test_xml_response(self):
        with CaseSpider() as spider:
            spider.start_requests('''
                yield scrapy.Request(
                    'data:text/xml,'
                    '<div><link><p>text</p></link></div>'
                )
            ''')
            spider.parse('''
                yield {
                    'v': response.css('div > link > p::text').extract_first()
                }
            ''')
            spider.record()
            spider.test()

    def test_reference_preservation(self):
        with CaseSpider() as spider:
            spider.start_requests('''
                yield scrapy.Request(
                    'data:text/plain,',
                )
            ''')
            spider.parse('''
                x = [1]
                item = {'data': x}
                yield scrapy.Request(
                    'data:text/plain,',
                    callback=self.second_callback,
                    meta={'x': x, 'item': item},
                    dont_filter=True
                )
            ''')
            spider.second_callback('''
                item = response.meta['item']
                x = response.meta['x']
                x.append(2)
                yield item  # should yield {'data': [1, 2]}
            ''')
            spider.record()
            spider.test()

    def test_fixture_length(self):
        class ModifiedSpider(CaseSpider):
            @property
            def template(self):
                return re.sub(
                    r'(scrapy_autounit)(\.)(AutounitMiddleware)',
                    r'tests.DelObjectsAutounitMiddleware',
                    super(ModifiedSpider, self).template)
        with ModifiedSpider() as spider:
            spider.set_init("""
        self.page_number = 0
        self.base_url = "http://www.example.com"
            """)
            spider.start_requests("""
                yield scrapy.Request('data:text/plain,', self.parse,
                                     meta={'test_attr': {'page_number': -1,
                                    'base_url': ''}})
            """)
            spider.parse("""
                yield {'a': 5}
            """)
            spider.record(record_verbosity=True)
            expected_message = "AssertionError: The fixture's data length "\
                               "doesn't match with the current callback's "\
                               "output length."
            with self.assertRaisesRegex(AssertionError,
                                        re.escape(expected_message)):
                spider.test(test_verbosity=True)

    def test_attribute_change_raises_error(self):
        class ModifiedSpider(CaseSpider):
            @property
            def template(self):
                return re.sub(
                    r'(scrapy_autounit)(\.)(AutounitMiddleware)',
                    r'tests.DelAttr\3', super(ModifiedSpider, self).template)

        with ModifiedSpider() as spider:
            spider.set_init("""self.page_number = 0""")
            spider.start_requests("""
                self.test_attr = 100 # attribute to be deleted
                yield scrapy.Request('data:text/plain,', self.parse)
            """)
            spider.parse("""
                self.page_number += 1
                yield {
                    'page_number': self.page_number
                }
                if self.page_number < 3:
                    yield scrapy.Request('data:text/plain,', dont_filter=True)
            """)
            spider.record()
            expected_message = """
    AssertionError: {'page_number': 1} != {'page_number': 1, 'test_attr': 100}
    - {'page_number': 1}
    + {'page_number': 1, 'test_attr': 100} : Output arguments not equal!"""
            with self.assertRaisesRegex(AssertionError,
                                        re.escape(expected_message)):
                spider.test(test_verbosity=True)
