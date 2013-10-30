import os
from setuptools import setup

README = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-extra-views',
    version='0.1',
    packages=['extra_views'],
    include_package_data=True,
    license='WTFPL',  # example license
    description='Additional Django generic views.',
    install_requires=['Django>=1.3'],
    long_description=README,
    url='http://www.icannhas.com/',
    author='Jayjay Montalbo',
    author_email='jayjay@icannhas.com',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: WTFPL',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
