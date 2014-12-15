#!/bin/env python
import ConfigParser
import re
import os
import json
import pickle
import logging

from bs4 import BeautifulSoup as bs4
import requests

from config import config
from session import session
from movie import Movie
from user import User
from torrent import Torrent

logger = logging.getLogger(__name__)

def login(**kwargs):
    """Simple helper function"""
    return API(**kwargs)

class PTPAPIException(Exception):
    """A generic exception to designate module-specific errors"""
    pass

class API:
    def __init__(self, username=None, password=None, passkey=None):
        j = None
        cookiesFile = config.get('Main', 'cookiesFile')
        logger.info("Initiating login sequence.")
        password = (password or config.get('PTP', 'password'))
        username = (username or config.get('PTP', 'username'))
        passkey = (passkey or config.get('PTP', 'passkey'))
        if os.path.isfile(cookiesFile):
            self.__load_cookies(cookiesFile)
            # A really crude test to see if we're logged in
            session.max_redirects = 1
            try:
                r = session.base_get('torrents.php')
            except requests.exceptions.TooManyRedirects:
                os.remove(cookiesFile)
                session.cookies = requests.cookies.RequestsCookieJar()
            session.max_redirects = 3
        if not os.path.isfile(cookiesFile):
            if not password or not passkey or not username:
                raise PTPAPIException("Not enough info provided to log in.")
            try:
                j = session.base_post('ajax.php?action=login',
                                 data={"username": username,
                                       "password": password,
                                       "passkey": passkey }).json()
            except ValueError as e:
                raise PTPAPIException("Could not parse returned json data.")
            if j["Result"] != "Ok":
                raise PTPAPIException("Failed to log in. Please check the username, password and passkey. Response: %s" % j)
            self.__save_cookie(cookiesFile)
            # Get some information that will be useful for later
            r = session.base_get('index.php')
        logger.info("Login successful.")
        self.current_user_id = re.search(r'user.php\?id=(\d+)', r.text).group(1)
        self.auth_key = re.search(r'auth=([0-9a-f]{32})', r.text).group(1)

    def logout(self):
        """Forces a logout."""
        cookiesFile = config.get('Main', 'cookiesFile')
        os.remove(cookiesFile)
        return session.base_get('logout.php', params={'auth': self.auth_key})

    def __save_cookie(self, cfile):        
        with open(cfile, 'w') as fh:
            logger.debug("Pickling HTTP cookies to %s" % cfile)
            pickle.dump(requests.utils.dict_from_cookiejar(session.cookies), fh)

    def __load_cookies(self, cfile):
        with open(cfile) as fh:
            logger.debug("Unpickling HTTP cookies from file %s" % cfile)
            session.cookies = requests.utils.cookiejar_from_dict(pickle.load(fh))

    def current_user(self):
        return User(self.current_user_id)

    def hnr_zip(self):
        return session.base_get('snatchlist.php', params={'action':'hnrzip'})
        
    def search(self, filters):
        if 'name' in filters:
            filters['searchstr'] = filters['name']
        filters['json'] = 'noredirect'
        ret_array = []
        for m in session.base_get('torrents.php', params=filters).json()['Movies']:
            if 'Directors' not in m:
                m['Directors'] = []
            if 'ImdbId' not in m:
                m['ImdbId'] = '0'
            ret_array.append(Movie(data=m))
        return ret_array

    def remove_snatched_bookmarks(self):
        session.base_post("bookmarks.php", data={'action': 'remove_snatched'})

    def remove_seen_bookmarks(self):
        session.base_post("bookmarks.php", data={'action': 'remove_seen'})

    def remove_uploaded_bookmarks(self):
        session.base_post("bookmarks.php", data={'action': 'remove_uploaded'})

    def need_for_seed(self):
        data = util.snarf_cover_view_data(session.base_get("needforseed.php").content)
        return [t['GroupingQualities'][0]['Torrents'][0] for t in data]

    def contest_leaders(self):
        logger.debug("Fetching contest leaderboard")
        soup = bs4(session.base_get("contestleaders.php").content)
        ret_array = []
        for cell in soup.find('table', class_='table--panel-like').find('tbody').find_all('tr'):
            ret_array.append((cell.find_all('td')[1].get_text(), cell.find_all('td')[2].get_text()))
        return ret_array
            

class Collection(object):
    def __init__(self, ID):
        self.ID = ID

class util(object):
    """A class for misc. utilities"""
    @staticmethod
    def snarf_cover_view_data(text):
        """Grab cover view data directly from an html source

        :param text: a raw html string
        :rtype: a dictionary of movie data"""
        data = []
        for d in re.finditer(r'coverViewJsonData\[\s*\d+\s*\]\s*=\s*({.*});', text):
            data.extend(json.loads(d.group(1))['Movies'])
        return data 

    @staticmethod
    def creds_from_conf(filename):
        """Pull user, password, and passkey information from a file

        :param filename: an absolute filename
        :rtype: a diction of the username, password and passkey"""
        config = ConfigParser.ConfigParser()
        config.read(filename)
        return { 'username': config.get('PTP', 'username'),
                 'password': config.get('PTP', 'password'),
                 'passkey': config.get('PTP', 'passkey') }
                 
                
