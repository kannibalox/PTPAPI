# flake8: noqa
"""Exists solely to make 'import ptpapi' possible"""
from ptpapi.api import API
from ptpapi.movie import Movie
from ptpapi.torrent import Torrent
from ptpapi.user import User


def login(**kwargs):
    """A helper function to make it easy to log in"""
    return API(**kwargs)
