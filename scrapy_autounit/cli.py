import os
import sys
import json
import scrapy
import argparse
from glob import glob
from datetime import datetime

from scrapy.utils.python import to_unicode
from scrapy.utils.project import inside_project, get_project_settings
from scrapy.commands.genspider import sanitize_module_name

from .player import Player
from .cassette import Cassette
from .recorder import Recorder
from .utils import get_base_path, get_project_dir


class CommandLine:
    def __init__(self, parser):
        self.parser = parser
        self.args = parser.parse_args()

        if not inside_project():
            self.error("No active Scrapy project")

        self.command = self.args.command

        self.spider = sanitize_module_name(self.args.spider)
        self.callback = self.args.callback
        self.fixture = self.args.fixture

        self.project_dir = get_project_dir()
        sys.path.append(self.project_dir)

        self.settings = get_project_settings()
        base_path = get_base_path(self.settings)
        self.tests_dir = os.path.join(base_path, 'tests')
        self.spider_dir = os.path.join(self.tests_dir, self.spider)

        if not os.path.isdir(self.spider_dir):
            self.error(
                "No recorded data found "
                "for spider '{}'".format(self.spider))

        extra_path = self.settings.get('AUTOUNIT_EXTRA_PATH') or ''
        self.callback_dir = os.path.join(
            self.spider_dir, extra_path, self.callback)

        if not os.path.isdir(self.callback_dir):
            self.error(
                "No recorded data found for callback "
                "'{}' from '{}' spider".format(self.callback, self.spider))

        if self.fixture:
            self.fixture_path = os.path.join(
                self.callback_dir, self.parse_fixture_arg())
            if not os.path.isfile(self.fixture_path):
                self.error("Fixture '{}' not found".format(self.fixture_path))

    def error(self, msg):
        print(msg)
        sys.exit(1)

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
        elif isinstance(data, (int, float)):
            return data
        return str(data)

    def inspect(self):
        cassette = Cassette.from_fixture(self.fixture_path)
        data = self.parse_data(cassette.to_dict())
        print(json.dumps(data))

    def update(self):
        to_update = []
        if self.fixture:
            to_update.append(self.fixture_path)
        else:
            target = os.path.join(self.callback_dir, "*.bin")
            to_update = glob(target)

        for path in to_update:
            player = Player.from_fixture(path)
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
        description="Updates fixtures to callback changes",
        formatter_class=argparse.RawTextHelpFormatter)
    update_cmd.add_argument('spider', help="The spider to update.")
    update_cmd.add_argument('callback', help="The callback to update.")
    update_cmd.add_argument('-f', '--fixture', help=(
        "The fixture to update.\n"
        "Can be the fixture number or the fixture name.\n"
        "If not specified, all fixtures will be updated."))

    cli = CommandLine(parser)
    cli.parse_command()
