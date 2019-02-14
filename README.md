# Scrapy Autounit

Scrapy Autounit is an automatic test generation tool for your Scrapy spiders.

## How it works?

Scrapy Autounit generates test fixtures and tests cases as you run your spiders.
The test fixtures are generated from the items and requests that your spider yields, then the test cases evaluate those fixtures against your spiders' callbacks.

Scrapy Autounit generates fixtures and tests per spider and callback under the Scrapy project root directory.  
Here is an example of the directory tree of your project once the tests are created:  
```
└── my_project
    ├── autounit
    │   ├── __init__.py
    │   ├── fixtures
    │   │   └── my_spider
    │   │       └── my_callback
    │   │           ├── fixture1.json
    │   │           ├── fixture2.json
    │   │           ├── ...
    │   └── tests
    │       ├── __init__.py
    │       └── my_spider
    │           ├── __init__.py
    │           └── my_callback
    │               ├── __init__.py
    │               ├── test_fixture1.py
    │               ├── test_fixture2.py
    │               ├── ...
    ├── scrapy.cfg
    └── my_project
        ├── __init__.py
        ├── items.py
        ├── middlewares.py
        ├── pipelines.py
        ├── settings.py
        └── spiders
            ├── __init__.py
            └── my_spider.py
```

## Installation

```
pip install scrapy_autounit
```

## Usage

First, add the spider middleware to the end of your `SPIDER_MIDDLEWARES` setting.  
For now, it should be the last spider middleware in your list by numeric order (better middleware support coming soon):
```python
SPIDER_MIDDLEWARES = {
    'scrapy_autounit.AutounitMiddleware': 900
}
```
Then make sure you enable Scrapy Autounit:
```python
AUTOUNIT_ENABLED = True
```
**NOTE:** Make sure you turn AUTOUNIT_ENABLED on only when you are generating/updating fixtures/tests, otherwise it should be off.

### Generating tests
To generate your fixtures and tests just run your spiders as usual, Scrapy Autounit will generate them for you.  
If you want to **update** your tests and fixtures you only need to run your spiders again.
### Running tests
To run your tests you can use `unittest` regular commands.
###### Test all
```
python -m unittest
```
###### Test a specific spider
```
python -m unittest discover -s autounit.tests.my_spider
```
###### Test a specific callback
```
python -m unittest discover -s autounit.tests.my_spider.my_callback
```
###### Test a specific fixture
```
python -m unittest autounit.tests.my_spider.my_callback.test_fixture2
```

## Settings

**AUTOUNIT_ENABLED**  
Set this to `True` or `False` to enable or disable unit test generation.

**AUTOUNIT_MAX_FIXTURES_PER_CALLBACK**  
Sets the maximum number of fixtures to store per callback.  
Minimum: 10  
Default: 10

**AUTOUNIT_EXCLUDED_FIELDS**  
Sets a list of fields to be excluded when recording your callbacks' items. It's useful to bypass fields that return a different value on each run.  
For example if you have a field that is always set to `datetime.now()` in your spider, you probably want to add that field to this list to be excluded from fixtures. Otherwise you'll get a different value when you're generating your fixtures than when you're running your tests, making your tests fail.  
Default: []

**AUTOUNIT_SKIPPED_FIELDS**  
Sets a list of item fields to be skipped when running your tests.  
It's very similar to AUTOUNIT_EXCLUDED_FIELDS with the difference that these fields will still be recorded in fixtures but they'll be skipped on tests.  
Default: []

**AUTOUNIT_REQUEST_SKIPPED_FIELDS**  
Sets a list of request fields to be skipped when running your tests.  
Similar to AUTOUNIT_SKIPPED_FIELDS but applied to requests instead of items.  
Default: []

**AUTOUNIT_EXCLUDED_HEADERS**  
Sets a list of headers to exclude from requests recording.  
For security reasons, Autounit already excludes `Authorization` and `Proxy-Authorization` headers by default.  
Default: []  

---
**Note**: Remember that you can always apply any of these settings per spider including them in your spider's `custom_settings` class attribute - see https://docs.scrapy.org/en/latest/topics/settings.html#settings-per-spider.
