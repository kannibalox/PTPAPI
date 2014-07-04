#!/bin/env python
from bs4 import BeautifulSoup as bs4
import requests
import ConfigParser
import re

session = requests.Session()
session.headers.update({"User-Agent": "Wget/1.13.4"})
baseURL = 'https://tls.passthepopcorn.me/'

class PTPAPIException(Exception):
    pass

class Movie:
    def __init__(self, ID=None, data=None):
        # Expects either a groupd ID to load data from, or for the data to already be present
        self.torrents = []
        if data:
            self.data = data
            self.ID = data['GroupId']
        elif ID:
            self.ID = ID
            self.data = {}
            self.load_data()
        else:
            raise PTPAPIException("Could not load necessary data for Movie class")
        if self.data['Torrents']:
            for t in self.data['Torrents']:
                self.torrents.append(Torrent(data=t))

    def load_data(self, basic=True, overwrite=False):
        # Check to see if data has already been set
        if not 'GroupId' in self.data or not overwrite:
            self.data = session.get(baseURL + "torrents.php",
                                    params={'id': self.ID,
                                            'json': '1'}).json()
            if self.data['Torrents']:
                for t in self.data['Torrents']:
                    self.torrents.append(Torrent(data=t))
        # Don't make two http calls unless told to
        if not basic and not overwrite:
            soup = bs4(session.get(baseURL + "torrents.php", params={'id':self.ID}).text)
            for t in self.torrents:
                # Get file list
                filediv = soup.find("div", id="files_%s" % t.ID)
                t.data['Filelist'] = {}
                for e in filediv.find("tbody").find_all("tr"):
                    bytesize = e("td")[1]("span")[0]['title'].replace(",","").replace(' bytes', '')
                    t.data['Filelist'][e("td")[0].string] = bytesize

class Torrent:
    def __init__(self, ID=None, data=None):
        if data:
            self.data = data
            self.ID = data['Id']
        elif ID:
            self.ID = ID
            self.load_data()
        else:
            raise PTPAPIException("Not enough information to intialize torrent")

    def load_data(self):
        # This has no 'basic' parameter, because it takes two calls to get the basic info anyway
        movieID = re.search(r'\?id=(\d+)', session.get(baseURL + 'torrents.php', params={'torrentid': self.ID}).url).group(1)
        self.data = session.get(baseURL + 'torrents.php',
                                params={'torrentid': self.ID,
                                        'id': movieID,
                                        'json':'1'})

    def download(self):
        r = session.get(baseURL + "torrents.php",
                        params={'action': 'download',
                                'id': self.ID})
        return r

class User:
    pass

class API:
    def __init__(self):
        pass

    def login(self, conf=None, username=None, password=None, passkey=None):
        if conf:
            config = ConfigParser.ConfigParser()
            config.read(conf)
            username = config.get('PTP', 'username')
            password = config.get('PTP', 'password')
            passkey = config.get('PTP', 'passkey')
        elif password and passkey and username:
            pass
        else:
            raise PTPAPIException("Not enough info provided to log in.")
        r = session.post(baseURL + 'ajax.php?action=login',
                         data={"username": username,
                               "password": password,
                               "passkey": passkey })
        if r.json()["Result"] != "Ok":
            raise PTPAPIException("Failed to log in. Please check the username, password and passkey. Response: %s" % r.json())
        return r.json()

    def logout(self):
        # This shouldn't require two calls
        authkey = session.get(baseURL + 'torrents.php?json=noredirect').json()['AuthKey']
        return session.get(baseURL + 'logout.php', params={'auth': authkey})
        
    def search(self, filters):
        if 'name' in filters:
            filters.update({'searchstr': filters['name']})
        filters.update({'json': 'noredirect'})
        return [Movie(data=m) for m in session.get(baseURL + 'torrents.php', params=filters).json()['Movies']]