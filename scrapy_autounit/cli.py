import argparse
import json
import os
import pickle
import re
import sys
from datetime import datetime
from glob import glob

import scrapy
from scrapy.commands.genspider import sanitize_module_name
from scrapy.utils.project import inside_project, get_project_settings
from scrapy.utils.python import to_unicode

from .cassette import Cassette
from .player import Player
from .recorder import Recorder, TEST_TEMPLATE
from .utils import get_base_path, get_project_dir, python_version


class CommandLine:
    def __init__(self, parser):
        self.parser = parser
        self.args = parser.parse_args()

        if not inside_project():
            self._error("No active Scrapy project")

        self.command = self.args.command

        self.spider = self.args.spider
        self.callback = self.args.callback
        self.fixture = self.args.fixture

        self.project_dir = get_project_dir()
        sys.path.append(self.project_dir)

        self.settings = get_project_settings()

        base_path = get_base_path(self.settings)
        self.tests_dir = os.path.join(base_path, 'tests')

        if self.spider:
            self.spider = sanitize_module_name(self.spider)
            self.callbacks_dir = self._get_callbacks_dir(self.spider)
            if not os.path.isdir(self.callbacks_dir):
                self._error("No recorded data found for spider '{}'".format(self.spider))

            if self.callback:
                self.callback_dir = os.path.join(self.callbacks_dir, self.callback)
                if not os.path.isdir(self.callback_dir):
                    self._error(
                        "No recorded data found for callback "
                        "'{}' from '{}' spider".format(self.callback, self.spider))

                if self.fixture:
                    self.fixture_path = os.path.join(self.callback_dir, self.parse_fixture_arg())
                    if not os.path.isfile(self.fixture_path):
                        self._error("Fixture '{}' not found".format(self.fixture_path))

    def _error(self, msg):
        print(msg)
        sys.exit(1)

    def _walk(self, root):
        for _, subdirs, _ in os.walk(root):
            for subdir in subdirs:
                if subdir == '__pycache__':
                    continue
                yield subdir

    def _get_callbacks_dir(self, spider):
        extra_path = self.settings.get('AUTOUNIT_EXTRA_PATH') or ''
        return os.path.join(self.tests_dir, spider, extra_path)

    def _get_spider_fixtures(self, callbacks_dir):
        fixtures = []
        for callback in self._walk(callbacks_dir):
            target = os.path.join(callbacks_dir, callback, '*.bin')
            fixtures.extend(glob(target))
        return fixtures

    def _from_legacy_fixture(self, recorded):
        encoding = recorded['encoding']
        old = pickle.loads(recorded['data'], encoding=encoding)
        new = Cassette()
        new.spider_name = old['spider_name']
        new.middlewares = old['middlewares']
        new.included_settings = old['settings']
        new.python_version = old.get('python_version', python_version())
        new.request = old['request']
        new.response = old['response']
        new.init_attrs = {}
        new.input_attrs = old.get('spider_args_in') or old.get('spider_args') or {}
        new.output_attrs = old.get('spider_args_out', {})
        new.output_data = old['result']
        return new

    def _update_legacy_test(self, path, cassette):
        path_dir = os.path.dirname(path)
        older_version_test = os.path.join(path_dir, 'test_fixture1.py')
        if os.path.isfile(older_version_test):
            to_remove = os.path.join(path_dir, 'test_fixture*.py')
            for test in glob(to_remove):
                if test == older_version_test:
                    os.rename(test, path)
                    continue
                os.remove(test)
        test_name = (
            sanitize_module_name(cassette.spider_name) + '__' +
            cassette.request['callback']
        )
        with open(path, 'r+') as f:
            old = f.read()
            command = 'Scrapy Autounit'
            command_re = re.search('# Generated by: (.*)  # noqa', old)
            if command_re:
                command = command_re.group(1)
            test_code = TEST_TEMPLATE.format(test_name=test_name, command=command)
            f.seek(0)
            f.write(test_code)
            f.truncate()

    def parse_fixture_arg(self):
        try:
            int(self.fixture)
            return 'fixture{}.bin'.format(self.fixture)
        except ValueError:
            pass
        if not self.fixture.endswith('.bin'):
            return '{}.bin'.format(self.fixture)
        return self.fixture

    def parse_data(self, data):
        if isinstance(data, (dict, scrapy.Item)):
            return {
                self.parse_data(k): self.parse_data(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self.parse_data(x) for x in data]
        elif isinstance(data, bytes):
            return to_unicode(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, (int, float, str)):
            return data
        return repr(data)

    def inspect(self):
        cassette = Cassette.from_fixture(self.fixture_path)
        data = self.parse_data(cassette.to_dict())
        print(json.dumps(data))

    def update(self):
        if self.callback and not self.spider:
            print("Must specify a spider")
            return

        if self.fixture and (not self.spider or not self.callback):
            print("Must specify a spider and a callback")
            return

        if not self.spider:
            print("WARNING: this will update all the existing fixtures from the current project")
            confirmation = input("Do you want to continue? (y/n) ")
            if confirmation.lower() != 'y':
                print("Update cancelled")
                return

        to_update = []
        if self.fixture:
            to_update.append(self.fixture_path)
        elif self.callback:
            target = os.path.join(self.callback_dir, "*.bin")
            to_update = glob(target)
        elif self.spider:
            to_update = self._get_spider_fixtures(self.callbacks_dir)
        else:
            for spider in self._walk(self.tests_dir):
                callbacks_dir = self._get_callbacks_dir(spider)
                to_update.extend(self._get_spider_fixtures(callbacks_dir))

        for path in to_update:
            player = Player.from_fixture(path)

            # Convert legacy fixtures to new cassette-based fixtures
            if isinstance(player.cassette, dict):
                print("Converting legacy fixture: {}".format(path))
                new_cassette = self._from_legacy_fixture(player.cassette)
                player.cassette = new_cassette
                test_path = os.path.join(os.path.dirname(path), 'test_fixtures.py')
                self._update_legacy_test(test_path, new_cassette)

            output, attrs = player.playback(compare=False)

            _, parsed = player.parse_callback_output(output)

            cassette = player.cassette
            cassette.output_data = parsed
            cassette.init_attrs = attrs['init']
            cassette.input_attrs = attrs['input']
            cassette.output_attrs = attrs['output']

            Recorder.update_fixture(cassette, path)

            print("Fixture '{}' successfully updated.".format(
                os.path.relpath(path)))

    def parse_command(self):
        if self.command == "inspect":
            self.inspect()
        elif self.command == "update":
            self.update()


def main():
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(help='Action commands', dest='command')
    subparsers.required = True

    inspect_cmd = subparsers.add_parser(
        'inspect',
        description="Inspects fixtures data returning a JSON object",
        formatter_class=argparse.RawTextHelpFormatter)
    inspect_cmd.add_argument('spider', help="The spider to update.")
    inspect_cmd.add_argument('callback', help="The callback to update.")
    inspect_cmd.add_argument('fixture', help=(
        "The fixture to update.\n"
        "Can be the fixture number or the fixture name."))

    update_cmd = subparsers.add_parser(
        'update',
        description="Updates fixtures and tests according to library and spider changes.",
        formatter_class=argparse.RawTextHelpFormatter)
    update_cmd.add_argument('-s', '--spider', help=(
        "The spider to update.\n"
        "If not specified, all the spiders from the current project will be updated."))
    update_cmd.add_argument('-c', '--callback', help=(
        "The callback to update.\n"
        "If not specified, all the callbacks from the specified spider will be updated."))
    update_cmd.add_argument('-f', '--fixture', help=(
        "The fixture to update.\n"
        "Can be the fixture number or the fixture name.\n"
        "If not specified, all the fixtures from the specified callback will be updated."))

    cli = CommandLine(parser)
    cli.parse_command()
