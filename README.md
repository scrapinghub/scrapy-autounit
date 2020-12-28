# Scrapy Autounit

[![AppVeyor](https://ci.appveyor.com/api/projects/status/github/scrapinghub/scrapy-autounit?branch=master&svg=true)](https://ci.appveyor.com/project/scrapinghub/scrapy-autounit/branch/master)
[![PyPI Version](https://img.shields.io/pypi/v/scrapy-autounit.svg?color=blue)](https://pypi.python.org/pypi/scrapy-autounit/)  
&nbsp;
## Documentation
- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
- [Caveats](#caveats)
- [Settings](#settings)
- [Command Line Interface](#command-line-interface)
- [Internals](#internals)  
&nbsp;

## Overview

Scrapy-Autounit is an automatic test generation tool for your Scrapy spiders.

It generates test fixtures and tests cases as you run your spiders.  

The fixtures are generated from the items and requests that your spider returns, then the test cases evaluate those fixtures against your spiders' callbacks.

Scrapy Autounit generates fixtures and tests per spider and callback under the Scrapy project root directory.  
Here is an example of the directory tree of your project once the fixtures are created:  
```
my_project
├── autounit
│   ├── __init__.py
│   └── tests
│       ├── __init__.py
│       └── my_spider
│           ├── __init__.py
│           └── my_callback
│               ├── __init__.py
│               ├── fixture1.bin
│               ├── fixture2.bin
│               ├── test_fixtures.py
├── my_project
│   ├── __init__.py
│   ├── items.py
│   ├── middlewares.py
│   ├── pipelines.py
│   ├── settings.py
│   └── spiders
│       ├── __init__.py
│       └── my_spider.py
└── scrapy.cfg
```
&nbsp;

## Installation

```
pip install scrapy_autounit
```
&nbsp;

## Usage

Add the spider middleware to your `SPIDER_MIDDLEWARES` setting (no specific order required):  
```python
SPIDER_MIDDLEWARES = {
    'scrapy_autounit.AutounitMiddleware': 950
}
```

### Generating tests
Make sure you enable Scrapy Autounit in your settings:
```python
AUTOUNIT_ENABLED = True
```
To generate your fixtures and tests just run your spiders as usual, Scrapy Autounit will generate them for you.  
```
$ scrapy crawl my_spider
```
When the spider finishes, a directory `autounit` is created in your project root dir, containing all the generated tests/fixtures for the spider you just ran (see the directory tree example above).  

If you want to **update** your tests and fixtures you only need to run your spiders again or use the [`autounit update`](#autounit-update) command line tool.

### Running tests
To run your tests you can use `unittest` regular commands.

###### Test all
```
$ python -m unittest discover autounit/tests/
```
###### Test a specific spider
```
$ python -m unittest discover autounit/tests/my_spider/
```
###### Test a specific callback
```
$ python -m unittest discover autounit/tests/my_spider/my_callback/
```
&nbsp;

## Caveats
- Keep in mind that as long as `AUTOUNIT_ENABLED` is on, each time you run a spider tests/fixtures are going to be generated for its callbacks.  
This means that if you have your tests/fixtures ready to go, this setting should be off to prevent undesired overwrites.  
Each time you want to regenerate your tests (e.g.: due to changes in your spiders), you can turn this on again and run your spiders as usual.  
For example, this setting should be off when running your spiders in Scrapy Cloud.  

- Autounit uses an internal `_autounit_cassette` key in requests' meta dictionaries. Avoid using/overriding this key in your spiders when adding data to meta to prevent unexpected behaviours.  
&nbsp;

## Settings

###### General

- **AUTOUNIT_ENABLED**  
Set this to `True` or `False` to enable or disable unit test generation.

- **AUTOUNIT_MAX_FIXTURES_PER_CALLBACK**  
Sets the maximum number of fixtures to store per callback.  
`Minimum: 10`  
`Default: 10`

- **AUTOUNIT_EXTRA_PATH**  
This is an extra string element to add to the test path and name between the spider name and callback name. You can use this to separate tests from the same spider with different configurations.  
`Default: None`

- **AUTOUNIT_FIXTURE_NAMING_ATTR**  
Allows you to specify a spider attribute to be used in your fixtures names.  
The fixture name will consist of your specified attribute value and the internal callback counter.  
`fixture_{your_spider_attr}_{internal_counter}.bin`  
If this settings is not specified, the default `fixtureN.bin` naming will be used.  
`Default: None`

###### Output

- **AUTOUNIT_DONT_TEST_OUTPUT_FIELDS**  
Sets a list of fields to be skipped from testing your callbacks' items. It's useful to bypass fields that return a different value on each run.  
For example if you have a field that is always set to `datetime.now()` in your spider, you probably want to add that field to this list to be skipped on tests. Otherwise you'll get a different value when you're generating your fixtures than when you're running your tests, making your tests fail.  
`Default: []`

###### Requests

- **AUTOUNIT_DONT_TEST_REQUEST_ATTRS**  
Sets a list of request attributes to be skipped when running your tests.  
`Default: []`

- **AUTOUNIT_DONT_RECORD_HEADERS**  
Sets a list of headers to exclude from requests recording.  
For security reasons, Autounit already excludes `Authorization` and `Proxy-Authorization` headers by default, if you want to record them in your fixtures see *`AUTOUNIT_RECORD_AUTH_HEADERS`*.  
`Default: []`  

- **AUTOUNIT_RECORD_AUTH_HEADERS**  
If you want to include `Authorization` or `Proxy-Authorization` headers in your fixtures, add one or both of them to this list.  
`Default: []`

- **AUTOUNIT_DONT_RECORD_META**  
Sets a list of jmespath-like keys to exclude from requests meta recording.  
These keys will not be recorded in autounit fixtures.  
Keys syntax supported so far: `single_key`, `key.subkey`, `key.list[]`, `key.list[].subkey`  
`Default: []`

- **AUTOUNIT_DONT_TEST_META**  
Same as `AUTOUNIT_DONT_RECORD_META` but this only skips the specified meta keys at the testing stage.  
The keys will be recorded in autounit fixtures.  
`Default: []`

###### Spider attributes

- **AUTOUNIT_DONT_RECORD_SPIDER_ATTRS**  
Sets a list of spider attributes that won't be recorded into your fixtures.  
`Default: []`

- **AUTOUNIT_DONT_TEST_SPIDER_ATTRS**  
Sets a list of spider attributes to be skipped from testing your callbacks. These attributes will still be recorded.  
`Default: []`

###### Settings

- **AUTOUNIT_RECORD_SETTINGS**  
Sets a list of settings names to be recorded in the generated test case.  
`Default: []`

---
**Note**: Remember that you can always apply any of these settings per spider including them in your spider's `custom_settings` class attribute - see https://docs.scrapy.org/en/latest/topics/settings.html#settings-per-spider.  
&nbsp;

## Command line interface

- [`autounit inspect`](#autounit-inspect): inspects fixtures returning a JSON object
- [`autounit update`](#autounit-update): updates fixtures to callback changes

### `autounit inspect`  

To inspect a fixture's data, you need to pass the spider, callback and fixture name to the command:
```
$ autounit inspect my_spider my_callback fixture3
```
The fixture can also be passed as a number indicating which fixture number to inspect like this:
```
$ autounit inspect my_spider my_callback 3
```
**Note:** It's highly recommended that your fixtures were generated with scrapy-autounit 0.0.22 or higher to inspect data.

#### Extracted Data
This command returns a JSON object that can be parsed with tools like `jq` to inspect specific blocks of data.  

The top-level keys of the JSON output are:  

***`spider_name`***  
The name of the spider.  

***`request`***  
The original request that triggered the callback.  

***`response`***  
The response obtained from the original request and passed to the callback.  

***`output_data`***  
The callback's output such as items and requests.  
_Same as ***`result`*** prior to v0.0.28._

***`middlewares`***  
The relevant middlewares to replicate when running the tests.  

***`settings`***  
The settings explicitly recorded by the *`AUTOUNIT_INCLUDED_SETTINGS`* setting.  

***`init_attrs`***  
The spider's attributes right after its _\_\_init\_\__ call.

***`input_attrs`***  
The spider's attributes right before running the callback.  
_Same as ***`spider_args`*** or ***`spider_args_in`*** prior to v0.0.28._

***`output_attrs`***  
The spider's attributes right after running the callback.  
_Same as ***`spider_args_out`*** prior to v0.0.28._

Then for example, to inspect a fixture's specific request we can do the following:
```
$ autounit inspect my_spider my_callback 4 | jq '.request'
```

### `autounit update`

This command updates your fixtures to match your latest changes, avoiding to run the whole spider again.  
You can update the whole project, an entire spider, just a callback or a single fixture.  

###### Update the whole project
```
$ autounit update
WARNING: this will update all the existing fixtures from the current project
Do you want to continue? (y/n)
```

###### Update every callback in a spider
```
$ autounit update -s my_spider
```

###### Update every fixture in a callback
```
$ autounit update -s my_spider -c my_callback
```

###### Update a single fixture
```
# Update fixture number 5
$ autounit update -s my_spider -c my_callback -f 5
```
&nbsp;

## Internals

The `AutounitMiddleware` uses a [`Recorder`](scrapy_autounit/recorder.py) to record [`Cassettes`](scrapy_autounit/cassette.py) in binary fixtures.  

Then, the tests use a [`Player`](scrapy_autounit/player.py) to playback those `Cassettes` and compare its output against your current callbacks.  

The fixtures contain a pickled and compressed `Cassette` instance that you can get programmatically by doing:
```python
from scrapy_autounit.cassette import Cassette

cassette = Cassette.from_fixture(path_to_your_fixture)
# cassette.request
# cassette.response
# cassette.output_data
# ...
```

If you know what you're doing, you can modify that cassette and re-record it by using:
```python
from scrapy_autounit.recorder import Recorder

Recorder.update_fixture(cassette, path)
```
