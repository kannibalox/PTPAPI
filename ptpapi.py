#!/bin/env python
from bs4 import BeautifulSoup as bs4
import requests
import ConfigParser

session = requests.Session()
session.headers.update({"User-Agent": "Wget/1.13.4"})
baseURL = 'https://tls.passthepopcorn.me/'

class PTPAPIException(Exception):
    pass

class Movie:
    def __init__(self, ID=None, data=None):
        self.torrents = []
        if data:
            self.data = data
            self.ID = data['GroupId']
        elif ID:
            self.ID = ID
            self.load_data()
        if self.data['Torrents']:
            for t in self.data['Torrents']:
                self.torrents.append(Torrent(data=t))

    def load_info(self, basic=True):
        self.info = session.get(baseURL + "torrents.php",
                                    params={'id': self.ID,
                                            'json': '1'}).json()
        if self.data['Torrents']:
            for t in self.data['Torrents']:
                self.torrents.append(Torrent(data=t))
        if not basic:
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

    def download():
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