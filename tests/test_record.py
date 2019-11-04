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

    def start_requests(self):
        {start_requests}

    def parse(self, response):
        {parse}
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

    def start_requests(self, string):
        self._start_requests = string

    def parse(self, string):
        self._parse = string

    def _write_spider(self):
        with open(os.path.join(self.proj_dir, 'myspider.py'), 'w') as dest:
            dest.write(SPIDER_TEMPLATE.format(
                name=self._spider_name,
                start_requests=self._start_requests,
                parse=self._parse,
                imports=self._imports,
                custom_settings=self._custom_settings,
            ))

    def record(self, args=None, settings=None):
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
            cwd='/',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        check_process('Running spider failed!', result)
        if not any(
            any(f.endswith('.py') and f != '__init__.py' for f in files)
            for _, _, files in os.walk(os.path.join(self.dir, 'autounit'))
        ):
            process_error('No autounit tests recorded!', result)

    def test(self):
        if self._start_requests is None or self._parse is None:
            raise AssertionError()
        env = os.environ.copy()
        env['SCRAPY_SETTINGS_MODULE'] = 'myproject.settings'
        result = run(
            [
                'python', '-m', 'unittest', 'discover', '-v'
            ],
            cwd=self.dir,
            env=env,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        check_process('Unit tests failed!', result)
        err = result['stderr'].decode('utf-8')
        tests_ran = re.search('Ran ([0-9]+) test', err).group(1)
        if tests_ran == '0':
            def itertree():
                for root, dirs, files in os.walk(self.dir):
                    for f in files:
                        yield os.path.join(root, f)
            raise AssertionError(
                'No tests run!\nProject dir:\n{}'.format(
                    '\n'.join(itertree())
                ))


class TestRecording(unittest.TestCase):
    def test_normal(self):
        with CaseSpider() as spider:
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse('''
                yield {'a': 4}
            ''')
            spider.record()
            spider.test()

    def test_path_extra(self):
        with CaseSpider() as spider:
            spider.start_requests("yield scrapy.Request('data:text/plain,')")
            spider.parse('''
                yield {'a': 4}
            ''')
            spider.record(settings=dict(AUTOUNIT_EXTRA_PATH='abc'))
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
                    '<div><link><p>text_html</p></link></div>'
                )
            ''')
            spider.parse('''
                yield {
                    'v': response.css('div > link > p::text').get()
                }
            ''')
            spider.record()
            spider.test()

    def test_xml_response(self):
        with CaseSpider() as spider:
            spider.start_requests('''
                yield scrapy.Request(
                    'data:text/xml,'
                    """
                    <?xml version="1.0" encoding="UTF-8"?>
                        <note>
                            <to>Scrapinghub</to>
                            <from>Somebody</from>
                            <heading>Reminder</heading>
                            <body>Newsletter...</body>
                            </note>
                    """ 
                )
            ''')
            spider.parse('''
                yield {
                    'v': response.css('div > link > p::text').get()
                }
            ''')
            spider.record()
            spider.test()