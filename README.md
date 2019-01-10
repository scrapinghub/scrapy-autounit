# Scrapy Autounit

Scrapy Autounit is an automatic test generation tool for your Scrapy spiders.

## How it works?

Scrapy Autounit generates test fixtures and tests cases as you run your spiders.
The test fixtures are generated from the items that your spider yields, then the test cases evaluate those fixtures against your spiders' callbacks.

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

First add the spider middleware to your `SPIDER_MIDDLEWARES`:
```python
SPIDER_MIDDLEWARES = {
    'scrapy_autounit.AutounitMiddleware': 900
}
```
Then make sure you enable Scrapy Autounit:
```python
AUTOUNIT_ENABLED = True
```
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
python -m unittest discover -s autounit.tests.my_spider.my_callback.test_fixture2
```

## Settings

**AUTOUNIT_ENABLED**  
Set this to `True` or `False` to enable or disable unit test generation.

**AUTOUNIT_MAX_FIXTURES_PER_CALLBACK**  
Sets the maximum number of fixtures to store per callback.  
Minimum: 10  
Default: 10
