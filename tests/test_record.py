import unittest
import tempfile
import subprocess
import os


SPIDER_TEMPLATE = '''
import scrapy


class MySpider(scrapy.Spider):
    name = 'myspider'

    custom_settings = dict(
        SPIDER_MIDDLEWARES={{
            'scrapy_autounit.AutounitMiddleware': 950,
        }}
    )

    def start_requests(self):
        {start_requests}

    def parse(self, response):
        {parse}
'''


def indent(string):
    return '\n'.join('    ' + s for s in string.splitlines())


def process_error(message, result):
    if result.returncode == 0:
        return
    raise AssertionError(
        '{}\nSTDOUT--\n{}\nSTDERR--\n{}'.format(
            message,
            indent(result.stdout.decode('utf-8')),
            indent(result.stderr.decode('utf-8')),
        ))


class CaseSpider(object):
    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.proj_dir = os.path.join(self.dir.name, 'myproject')
        os.mkdir(self.proj_dir)
        with open(os.path.join(self.proj_dir, '__init__.py'), 'w'):
            pass
        with open(os.path.join(self.proj_dir, 'settings.py'), 'w') as dest:
            dest.write('SPIDER_MODULES = ["myproject"]\n')
        self._start_requests = None
        self._parse = None

    def __enter__(self):
        self.dir.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.dir.__exit__(exc_type, exc_value, traceback)

    def start_requests(self, string):
        self._start_requests = string
        self._write_spider()

    def parse(self, string):
        self._parse = string
        self._write_spider()

    def _write_spider(self):
        with open(os.path.join(self.proj_dir, 'myspider.py'), 'w') as dest:
            dest.write(SPIDER_TEMPLATE.format(
                start_requests=self._start_requests,
                parse=self._parse
            ))

    def record(self, args=None, settings=None):
        if self._start_requests is None or self._parse is None:
            raise AssertionError()
        env = os.environ.copy()
        env['PYTHONPATH'] = self.dir.name  # doesn't work if == cwd
        env['SCRAPY_SETTINGS_MODULE'] = 'myproject.settings'
        command_args = []
        for k, v in (args or {}).items():
            command_args.append('-a')
            command_args.append('{}={}'.format(k, v))
        for k, v in (settings or {}).items():
            command_args.append('-s')
            command_args.append('{}={}'.format(k, v))
        result = subprocess.run([
            'scrapy', 'crawl', 'myspider',
            '-s', 'AUTOUNIT_ENABLED=1',
            *command_args
        ], env=env, cwd='/', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_error('Running spider failed!', result)

    def test(self):
        if self._start_requests is None or self._parse is None:
            raise AssertionError()
        env = os.environ.copy()
        env['SCRAPY_SETTINGS_MODULE'] = 'myproject.settings'
        result = subprocess.run(
            [
                'python', '-m', 'unittest', 'discover', '-v'
            ],
            cwd=self.dir.name,
            env=env,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        process_error('Unit tests failed!', result)
        err = result.stderr.decode('utf-8')
        if 'Ran 1 test' not in err:
            def itertree():
                for root, dirs, files in os.walk(self.dir.name):
                    for f in files:
                        yield os.path.join(root, f)
            raise AssertionError(
                'No tests generated/read!\nProject dir:\n{}'.format(
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
