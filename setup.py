#!/usr/bin/env python
from setuptools import setup

setup(
    name="PTPAPI",
    version="0.3",
    install_requires=[
        "requests",
        "beautifulsoup4",
    ],
    extras_require={
        'reseed': ['guessit>=2']
    },
    packages=[
        'ptpapi',
    ],
    scripts=[
        'scripts/ptp',
        'scripts/ptp-reseed',
        'scripts/ptp-bookmarks',
    ],
)
