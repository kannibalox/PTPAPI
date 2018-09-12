#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name="PTPAPI",
    version="0.5",
    author="kannibalox",
    url="https://github.com/kannibalox/PTPAPI",
    install_requires=[
        "requests",
        "beautifulsoup4",
        "tempita",
        "six"
    ],
    extras_require={
        'reseed': ['guessit>=2']
    },
    packages=find_packages('src'),
    package_dir={'':'src'},
    license='MIT',
    entry_points={
        'console_scripts': [
            'ptp=ptpapi.scripts.ptp:main',
            'ptp-reseed=ptpapi.scripts.ptp_reseed:main',
            'ptp-reseed-machine=ptpapi.scripts.ptp_reseed_machine:main',
        ],
    }
)
