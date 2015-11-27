# flake8: noqa
from api import API
from torrent import Torrent
from movie import Movie
from user import User


def login(username=None, password=None, passkey=None):
    return API(username, password, passkey)
