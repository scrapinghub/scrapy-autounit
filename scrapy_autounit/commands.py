from __future__ import print_function

import os
import sys
from scrapy_autounit.utils import get_project_dir


def update():
    project_dir = get_project_dir()
    if not project_dir:
        print('No active Scrapy project')
        sys.exit(1)

    tests_dir = os.path.join(project_dir, 'autounit/tests')
    for root, _, files in os.walk(tests_dir):
        tests = [f for f in files if f.endswith('.py') and f != '__init__.py']
        for test in tests:
            test_path = os.path.join(root, test)
            print('Updating test {}...'.format(test_path), end='')
            with open(test_path, 'r+') as f:
                content = f.read()
                new_content = content.replace(
                    'test_generator', 'generate_test')
                f.seek(0)
                f.write(new_content)
                f.truncate()
            print('OK')
