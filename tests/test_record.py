import unittest
import tempfile
import subprocess
import os
import shutil
import re

SPIDER_TEMPLATE = '''
import scrapy


class MySpider(scrapy.Spider):
    name = 'myspider'

    custom_settings = dict(
        SPIDER_MIDDLEWARES={{
            '{autonit_module_path}': 950,
        }}
    )

    def start_requests(self):
        {start_requests}

    def parse(self, response):
        {parse}

    def parse_item(self):
        {parse_item}
'''


def run(*pargs, **kwargs):
    proc = subprocess.run(*pargs, **kwargs)
    return {
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
    }


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
        # The test is performed in the files not in the installed package.
        # Replace path of modules for the test to reference the local path
        # where the files are copied: scrapy_autounit.utils -> .utils
        self.autounit_module_path = (
            '{}.middleware.AutounitMiddleware'.format('myproject'))
        self.autounit_utils_path = (
            '{}.utils'.format('myproject'))
        self.autounit_paths_update = {
            'scrapy_autounit.AutounitMiddleware': self.autounit_module_path,
            'scrapy_autounit.utils': self.autounit_utils_path,
        }
        self._write_mw()
        self._start_requests = None
        self._parse = None
        self._parse_item = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        shutil.rmtree(self.dir)

    def start_requests(self, string):
        self._start_requests = string
        self._write_spider()

    def parse(self, string):
        self._parse = string
        self._write_spider()

    def parse_item(self, string):
        self._parse_item = string
        self._write_spider()

    def _write_spider(self):
        spider_folder = os.path.join(self.proj_dir, 'spiders')
        self.spider_folder = spider_folder
        if not os.path.exists(spider_folder):
            os.mkdir(spider_folder)
        with open(os.path.join(spider_folder, 'myspider.py'), 'w') as dest:
            self.spider_text = SPIDER_TEMPLATE.format(
                start_requests=self._start_requests,
                parse=self._parse,
                parse_item= self._parse_item,
                autonit_module_path=self.autounit_module_path,
            )
            dest.write(self.spider_text)
            # print(self.spider_text)
        with open(os.path.join(spider_folder, '__init__.py'), 'w') as dest:
            dest.write("")

    def _write_mw(self):
        mw_folder = self.proj_dir
        self.mw_folder = mw_folder
        if not os.path.exists(mw_folder):
            os.mkdir(mw_folder)
        for item in os.listdir('scrapy_autounit'):
            if item.endswith('.py') and item != '__init__.py':
                s = os.path.join('scrapy_autounit', item)
                d = os.path.join(mw_folder, item)
                with open(s, 'r') as file:
                    file_text = file.read()
                for k, v in self.autounit_paths_update.items():
                    file_text = file_text.replace(k, v)
                with open(d, 'w') as dest:
                    dest.write(file_text)

    def record(self, args=None, settings=None):
        if self._start_requests is None or self._parse is None:
            raise AssertionError()
        env = os.environ.copy()
        env['PYTHONPATH'] = self.dir  # doesn't work if == cwd
        env['SCRAPY_SETTINGS_MODULE'] = 'myproject.settings'
        command_args = [
            'scrapy', 'crawl', 'myspider',
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
            stderr=subprocess.PIPE,
        )
        check_process('Running spider failed!', result)
        # print_test_output(result)
        if not os.path.exists(os.path.join(self.dir, 'autounit')):
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
        print_test_output(result)
        err = result['stderr'].decode('utf-8')
        num_tests = re.findall(r'Ran (\d+) test', err)
        is_ok = re.findall('OK$', err)
        if (not is_ok or not num_tests or (
                isinstance(num_tests, list) and int(num_tests[0]) == 0)):
            raise AssertionError(
                'No tests run!\nProject dir:\n{}'.format(
                    '\n'.join(itertree(self.dir))
                ))


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
                AUTOUNIT_EXCLUDED_ATTRIBUTES='start_urls',
                AUTOUNIT_INCLUDED_SETTINGS='AUTOUNIT_EXCLUDED_ATTRIBUTES'))
            spider.test()

        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                self.param2 = 1
                yield {'a': 4}
            """)
            spider.record(settings=dict(
                AUTOUNIT_EXCLUDED_ATTRIBUTES='start_urls,_base_url',
                AUTOUNIT_INCLUDED_SETTINGS='AUTOUNIT_EXCLUDED_ATTRIBUTES'))
            spider.test()

        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                self.param2 = 1
                yield {'a': 4}
            """)
            spider.record(settings=dict(
                AUTOUNIT_EXCLUDED_ATTRIBUTES='start_.*,_base_url',
                AUTOUNIT_INCLUDED_SETTINGS='AUTOUNIT_EXCLUDED_ATTRIBUTES'))
            spider.test()

        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                self.param2 = 1
                yield {'a': 4}
            """)
            spider.record(settings=dict(
                AUTOUNIT_EXCLUDED_ATTRIBUTES='start_date,__base_url',
                AUTOUNIT_INCLUDED_SETTINGS='AUTOUNIT_EXCLUDED_ATTRIBUTES'))
            spider.test()

        # Test invalid list formats
        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                self.param2 = 1
                yield {'a': 4}
            """)

            spider.record(settings=dict(
                AUTOUNIT_EXCLUDED_ATTRIBUTES=['start_date', '__base_url'],
                AUTOUNIT_INCLUDED_SETTINGS='AUTOUNIT_EXCLUDED_ATTRIBUTES'))

            with self.assertRaises(AssertionError):
                spider.test()

        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                self.param2 = 1
                yield {'a': 4}
            """)
            spider.record(settings=dict(
                AUTOUNIT_EXCLUDED_ATTRIBUTES=['start_date', '__base_url']))
            with self.assertRaises(AssertionError):
                spider.test()

    def test_spider_attributes_recursive(self):
        with CaseSpider() as spider:
            spider.start_requests("""
                self._base_url = 'www.nothing.com'
                yield scrapy.Request('data:text/plain,')
            """)
            spider.parse("""
                self.param = 1
                yield from self.parse_item()
            """)
            spider.parse_item("""
                self.__page = getattr(self, '__page', 0) + 1
                if self.__page > 3:
                    return
                for i in range(2):
                    yield scrapy.Request('data:text/plain,',
                                         callback=self.parse)
                                         """)
            spider.record()
            spider.test()
            print(spider.spider_text)
