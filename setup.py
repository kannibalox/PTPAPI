#!/usr/bin/env python
from setuptools import setup

setup(
    name="PTPAPI",
    version="0.3",
    install_requires=[
        "requests",
        "beautifulsoup4",
    ],
    packages=[
        'ptpapi',
        'ptpapi.cgapi',
    ],
    scripts=[
        'scripts/download.py',
        'scripts/bookmarks.py',
    ],
)