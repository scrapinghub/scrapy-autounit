# Scrapy Autounit

Scrapy Autounit is an automatic test generation tool for your Scrapy spiders.

## How it works?

Scrapy Autounit generates test fixtures and tests cases as you run your spiders.  
The test fixtures are generated from the items and requests that your spider yields, then the test cases evaluate those fixtures against your spiders' callbacks.

Scrapy Autounit generates fixtures and tests per spider and callback under the Scrapy project root directory.  
Here is an example of the directory tree of your project once the tests are created:  
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
│               ├── test_fixture1.py
│               ├── test_fixture2.py
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

## Installation

```
pip install scrapy_autounit
```

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
If you want to **update** your tests and fixtures you only need to run your spiders again.

### Running tests
To run your tests you can use `unittest` regular commands.

###### Test all
```
$ python -m unittest
```
###### Test a specific spider
```
$ python -m unittest discover -s autounit.tests.my_spider
```
###### Test a specific callback
```
$ python -m unittest discover -s autounit.tests.my_spider.my_callback
```
###### Test a specific fixture
```
$ python -m unittest autounit.tests.my_spider.my_callback.test_fixture2
```

## Caveats
- Keep in mind that as long as `AUTOUNIT_ENABLED` is on, each time you run a spider tests/fixtures are going to be generated for its callbacks.  
This means that if you have your tests/fixtures ready to go, this setting should be off to prevent undesired overwrites.  
Each time you want to regenerate your tests (e.g.: due to changes in your spiders), you can turn this on again and run your spiders as usual.  

- Autounit uses an internal `_autounit` key in requests' meta dictionaries. Avoid using/overriding this key in your spiders when adding data to meta to prevent unexpected behaviours.  

## Settings

**AUTOUNIT_ENABLED**  
Set this to `True` or `False` to enable or disable unit test generation.

**AUTOUNIT_MAX_FIXTURES_PER_CALLBACK**  
Sets the maximum number of fixtures to store per callback.  
`Minimum: 10`  
`Default: 10`

**AUTOUNIT_SKIPPED_FIELDS**  
Sets a list of fields to be skipped from testing your callbacks' items. It's useful to bypass fields that return a different value on each run.  
For example if you have a field that is always set to `datetime.now()` in your spider, you probably want to add that field to this list to be skipped on tests. Otherwise you'll get a different value when you're generating your fixtures than when you're running your tests, making your tests fail.  
`Default: []`

**AUTOUNIT_REQUEST_SKIPPED_FIELDS**  
Sets a list of request fields to be skipped when running your tests.  
Similar to AUTOUNIT_SKIPPED_FIELDS but applied to requests instead of items.  
`Default: []`

**AUTOUNIT_EXCLUDED_HEADERS**  
Sets a list of headers to exclude from requests recording.  
For security reasons, Autounit already excludes `Authorization` and `Proxy-Authorization` headers by default, if you want to include them in your fixtures see *`AUTOUNIT_INCLUDED_AUTH_HEADERS`*.  
`Default: []`  

**AUTOUNIT_INCLUDED_AUTH_HEADERS**  
If you want to include `Authorization` or `Proxy-Authorization` headers in your fixtures, add one or both of them to this list.  
`Default: []`

**AUTOUNIT_INCLUDED_SETTINGS**  
Sets a list of settings names to be recorded in the generated test case.  
`Default: []`

**AUTOUNIT_EXTRA_PATH**  
This is an extra string element to add to the test path and name between the spider name and callback name. You can use this to separate tests from the same spider with different configurations.  
`Default: None`

---
**Note**: Remember that you can always apply any of these settings per spider including them in your spider's `custom_settings` class attribute - see https://docs.scrapy.org/en/latest/topics/settings.html#settings-per-spider.

## Inspecting Data

To inspect the data recorded in the binary fixtures you can use `autounit-inspect` command line tool.  
It's highly recommended that your fixtures were generated with scrapy-autounit 0.0.22 or higher to use this tool.  

##### Usage

It has 2 ways of usage, passing a full path to the fixture we want to inspect with the `-p` argument:
```
$ autounit-inspect -p /path/to/your/fixtureN.bin
```
Or passing the spider, callback and fixture name you want to inspect:
```
$ autounit-inspect -s my_spider -c my_callback -f fixture3
```
The fixture can also be passed as a number indicating which fixture number to inspect like this:
```
$ autounit-inspect -s my_spider -c my_callback -f 3
```

##### Extracted Data
Any of these commands return a JSON object that can be parsed with tools like `jq` to inspect specific blocks of data.  

The top-level keys of the JSON output are:  

***spider_name***  
The name of the spider.  

***request***  
The original request that triggered the callback.  

***response***  
The response obtained from the original request and passed to the callback.  

***result***  
The callback's output such as items and requests.  

***middlewares***  
The relevant middlewares to replicate when running the tests.  

***settings***  
The settings explicitly recorded by the *`AUTOUNIT_INCLUDED_SETTINGS`* setting.  

***spider_args***  
The arguments passed to the spider in the crawl.  

***python_version***  
Indicates if the fixture was recorded in python 2 or 3.  

---
Then for example, to inspect a fixture's specific request we can do the following:
```
$ autounit-inspect -s my_spider -c my_callback -f 4 | jq '.request'
```
