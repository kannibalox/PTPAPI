import os
import re
import argparse
import json
import ConfigParser

import requests
from bs4 import BeautifulSoup

from config import config
from session import session

class KGAPI:
    HttpHeader = { "User-Agent": "Wget/1.13.4" }

    def __init__(self):
        self.baseURL = "https://karagarga.net"
        self.loggedIn = False

    def login(self, username=None, password=None, passkey=None):
        password = (password or config.get('KG', 'password'))
        username = (username or config.get('KG', 'username'))
        response = session.post(self.baseURL + "/takelogin.php",
                                data = {"username": username,
                                        "password": password}).text
        if response.find( 'action="takelogin.php"' ) != -1:
            print response
            raise KGAPIException("Failed to log in")
        self.loggedIn = True

    def search(self, search_args):
        search_string = '&'.join([ "%s=%s" % (key, value) for (key, value) in search_args.items() ])
        soup = self.__httpRequest('/browse.php?%s' % search_string)
        return self.getTorrentListInfo(soup)

    def getTorrentListInfo(self, soup):
        if not soup.find('table', id='browse'):
            return []
        retArray = []
        for row in soup.find('table', id='browse').find_all('tr')[1:]:
            if 'id' in row.find_all('td')[0].attrs:
                # Only rows used for displaying extra info have IDs; we don't want them
                continue
            cells = row.find_all('td')
            infoDict = {
                'Title': cells[1].b.get_text(),
                'Year': cells[3].get_text(),
                'Seeders': cells[12].get_text(),
                'Leechers': cells[13].get_text(),
                'Size': cells[10].get_text(),
            }
            infoDict['ID'] = re.search(r'\d+', cells[1].a['href']).group(0)
            retArray.append(infoDict)
        return retArray

    def download(self, ID):
        r = session.get(self.baseURL + "/down.php/%s/file.torrent" % ID)
        downloadName = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        return (downloadName, r.content)

    def downloadTorrent(self, ID, dest=None, name=None):
        if not dest:
            dest = os.getcwd()
        r = session.get(self.baseURL + "/down.php/%s/file.torrent" % ID)
        if not name:
            name = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        with open(os.path.join(dest, name), 'wb') as fh:
            fh.write(r.content)
        return os.path.join(dest, name)

    def __httpRequest(self, url, data=None):
        if not self.loggedIn:
            print "Not logged in"
            return None
        html = self.__request(self.baseURL + url, data)
        soup = BeautifulSoup(html, "html.parser")
        return soup

    def __request(self, url, data=None):
        return session.get(url, data=data).text

    def __jsonRequest(self, url, data=None):
        if not self.loggedIn:
            print "Not logged in"
            return None
        return session.get(url, data=data).json()

class KGAPIException(Exception):
    pass

if __name__ == '__main__':
    kg = KGAPI()
    kg.login()
    print kg.download(kg.search({'search_type': 'imdb', 'search': 'tt0126237'})[0]['ID'])
