import re
import argparse
import json
import ConfigParser

import requests
from bs4 import BeautifulSoup

from config import config
from session import session

class CGAPI:
    HttpHeader = { "User-Agent": "Wget/1.13.4" }

    def __init__(self):
        self.baseURL = "http://cinemageddon.net"
        self.loggedIn = False

    def login(self, username=None, password=None, passkey=None):
        password = (password or config.get('CG', 'password'))
        username = (username or config.get('CG', 'username'))
        response = session.post(self.baseURL + "/takelogin.php",
                                data = {"username": username,
                                        "password": password}).text
        if response.find( 'action="takelogin.php"' ) != -1:
            print response
            raise CGAPIException("Failed to log in")
        self.loggedIn = True

    def search(self, search_args):
        search_string = '&'.join([ "%s=%s" % (key, value) for (key, value) in search_args.items() ])
        soup = self.__httpRequest('/browse.php?%s' % search_string)
        return self.getTorrentListInfo(soup)

    def getTorrentListInfo(self, soup):
        if not soup.find('table', class_='torrenttable'):
            return []
        rows = soup.find('table', class_='torrenttable').find('tbody').find_all('tr')
        retArray = []
        for r in rows:
            data = {}
            data['Title'] = r.find('a', href=re.compile('details.php\?id=[0-9]+$'))['title']
            data['Size'] = r.find(text=re.compile('[0-9]+\.[0-9]+ [A-Z]B'))
            data['Seeders'] = re.match(r'([0-9]+)', r.find(title=re.compile('[0-9]+ seeders?'))['title']).group(1)
            data['ID'] = re.match(r'details.php\?id=([0-9]+)$', r.find('a', href=re.compile('details.php\?id=[0-9]+$'))['href']).group(1)
            retArray.append(data)
        return retArray

    def downloadTorrent(self, tID, name=None):
        r = session.get(self.baseURL + '/download.php', params={'id': tID})
        if not name:
            name = str(tID) + '.torrent'
        with open(name.replace('/', '_'), 'wb') as fh:
            fh.write(r.content)

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

class CGAPIException(Exception):
    pass

if __name__ == '__main__':
    cg = CGAPI()
    cg.login()
    print cg.search({'search': 'tt0111512'})
