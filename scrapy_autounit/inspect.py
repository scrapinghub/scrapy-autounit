import sys
import json
import scrapy
import argparse
from pathlib import Path
from datetime import datetime
from scrapy.utils.project import inside_project
from scrapy.utils.python import to_unicode
from scrapy_autounit.utils import (
    unpickle_data,
    decompress_data,
    get_project_dir,
    get_project_settings,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s',
        '--spider',
        help='The spider where to look fixtures for'
    )
    parser.add_argument(
        '-c',
        '--callback',
        help='The callback where to look fixtures for (requires spider)'
    )
    parser.add_argument(
        '-f',
        '--fixture',
        help=(
            'The fixture number to inspect (requires spider and callback).'
            'It can be an integer indicating the fixture number or a string'
            'indicating the fixture name'
        )
    )
    parser.add_argument(
        '-p',
        '--path',
        help='The full path for the fixture to inspect'
    )

    args = parser.parse_args()

    if args.path:
        retcode = handle_path(args.path)
        sys.exit(retcode)

    if not inside_project():
        print('No active Scrapy project')
        sys.exit(1)

    if not args.spider:
        print('Must specify a spider')
        parser.print_help()
        sys.exit(1)

    if not args.callback:
        print('Must specify a callback')
        parser.print_help()
        sys.exit(1)

    if not args.fixture:
        print('Must specify a fixture')
        parser.print_help()
        sys.exit(1)

    settings = get_project_settings()
    base_path = Path(settings.get(
        'AUTOUNIT_BASE_PATH',
        default=get_project_dir() / 'autounit'
    ))

    tests_dir = base_path / 'tests'

    if not Path.is_dir(tests_dir):
        print('Autounit tests directory not found\n')
        sys.exit(1)

    args.fixture = parse_fixture_arg(args.fixture)

    extra_path = settings.get('AUTOUNIT_EXTRA_PATH') or ''
    path = tests_dir / args.spider / extra_path / args.callback / args.fixture

    retcode = handle_path(path)
    sys.exit(retcode)


def parse_fixture_arg(arg):
    try:
        int(arg)
        return 'fixture{}.bin'.format(arg)
    except ValueError:
        pass
    if not arg.endswith('.bin'):
        return '{}.bin'.format(arg)
    return arg


def handle_path(path):
    if not Path(path).is_file():
        print("Fixture '{}' not found".format(path))
        return 1
    data = get_data(path)
    print(json.dumps(parse_data(data)))
    return 0


def get_data(path):
    with open(path, 'rb') as f:
        raw_data = f.read()

    fixture_info = unpickle_data(decompress_data(raw_data), 'utf-8')
    if 'fixture_version' in fixture_info:
        encoding = fixture_info['encoding']
        data = unpickle_data(fixture_info['data'], encoding)
    else:
        data = fixture_info  # legacy tests (not all will work, just utf-8)

    return parse_data(data)


def parse_data(data):
    if isinstance(data, (dict, scrapy.Item)):
        return {parse_data(k): parse_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [parse_data(x) for x in data]
    elif isinstance(data, bytes):
        return to_unicode(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, (int, float)):
        return data
    return str(data)
