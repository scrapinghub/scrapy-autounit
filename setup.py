import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='scrapy-autounit',
    version='0.0.21',
    author='',
    author_email='',
    description='Automatic unit test generation for Scrapy.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/fcanobrash/scrapy-autounit',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
    ],
    install_requires=[
        'pathlib',
        'datadiff==2.0.0',
    ],
    entry_points = {
        'console_scripts': ['autounit-inspect=scrapy_autounit.inspect:main'],
    },
)
