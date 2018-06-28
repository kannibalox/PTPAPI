# flake8: noqa
"""Exists solely to make 'import ptpapi' possible"""
from ptpapi.api import API
from ptpapi.torrent import Torrent
from ptpapi.movie import Movie
from ptpapi.user import User

def login(username=None, password=None, passkey=None):
    """A helper function to make it easy to log in"""
    return API(username, password, passkey)
