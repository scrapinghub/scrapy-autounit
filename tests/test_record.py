import os
import re
import shutil
import subprocess
import tempfile
import unittest

SPIDER_TEMPLATE = '''
import scrapy
{imports}


class MySpider(scrapy.Spider):
    name = '{name}'

    custom_settings = dict(
        SPIDER_MIDDLEWARES={{
            '{autonit_module_path}': 950,
        }},
        {custom_settings}
    )

    def start_requests(self):
        {start_requests}

    def parse(self, response):
        {parse}

    def parse_item(self):
        {parse_item}
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
        # Modification: the test is performed using the local middleware files,
        # not on the installed package.
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
        self._spider_name = 'myspider'
        self._imports = ''
        self._custom_settings = ''

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        shutil.rmtree(self.dir)

    @property
    def spider_text(self):
        return self._spider_text

    def set_spider_text(self):
        self._spider_text = SPIDER_TEMPLATE.format(
            name=self._spider_name,
            start_requests=self._start_requests,
            parse=self._parse,
            parse_item=self._parse_item,
            imports=self._imports,
            custom_settings=self._custom_settings,
            autonit_module_path=self.autounit_module_path,
        )

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

    def parse_item(self, string):
        self._parse_item = string

    def _reformat_custom_spider(self, string):
        m = re.search(r'(?<=class )([\w\s]+)(?=\(.*\)\:)', string)
        spider_name = m.group() if m else ''
        _text = re.sub(re.escape(spider_name), r'MySpider', string)
        _text = re.sub(r'(name\s*\=\s*[\"\']+)(.*)([\"\']+)', r'\1myspider\3',
                       _text)
        _text = self._update_paths_in_text(_text)
        return _text

    def _update_paths_in_text(self, string):
        for k, v in self.autounit_paths_update.items():
            string = string.replace(k, v)
        return string

    def _write_generic_spider(self, string):
        # Override the value in set_spider_text in order to have
        # generic spiders
        self._spider_text = self._reformat_custom_spider(string)
        # Avoid error raised for the spider with template in self.record
        self._start_requests = True
        self._parse = True
        self._write_spider()

    def _write_spider(self):
        spider_folder = os.path.join(self.proj_dir, 'spiders')
        self.spider_folder = spider_folder
        if not os.path.exists(spider_folder):
            os.mkdir(spider_folder)
        with open(os.path.join(spider_folder, 'myspider.py'), 'w') as dest:
            dest.write(self.spider_text)
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
                file_text = self._update_paths_in_text(file_text)
                with open(d, 'w') as dest:
                    dest.write(file_text)

    def record(self, args=None, settings=None, record_verbosity=False):
        self.set_spider_text()
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
            stderr=subprocess.PIPE,
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
            cwd=self.dir,
            env=env,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        check_process('Unit tests failed!', result)
        err = result['stderr'].decode('utf-8')
        tests_ran = re.search('Ran ([0-9]+) test', err).group(1)

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
                reqs = self.parse_item()
                for r in reqs:
                    yield r
            """)
            spider.parse_item("""
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
                reqs = self.parse_item()
                for r in reqs:
                    yield r
            """)
            spider.parse_item("""
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

        # Testing spider with rescursive spiders
        with CaseSpider() as spider:
            spider._write_generic_spider("""
import scrapy


class HijSpider(scrapy.Spider):
    name = 'hij'

    custom_settings = dict(
        SPIDER_MIDDLEWARES={
            'myproject.middleware.AutounitMiddleware': 950,
        }
    )

    def __init__(self, *pargs, **kwargs):
        super(HijSpider, self).__init__(*pargs, **kwargs) # py 2.7 compatible
        self.i = 0

    def start_requests(self):
        yield self.next_req()

    def next_req(self):
        self.i += 1
        return scrapy.Request('data:text/plain,hi', dont_filter=True)

    def parse(self, response):
        if self.i < 3:
            yield self.next_req()

                """)

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
