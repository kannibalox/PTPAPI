import re
import urllib
import urllib2
import cookielib
import argparse
import json
import ConfigParser

import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({"User-Agent": "Wget/1.13.4"})

class CGAPI:
    HttpHeader = { "User-Agent": "Wget/1.13.4" }

    def __init__(self):
        self.baseURL = "http://cinemageddon.net"
        self.__cookieJar = cookielib.CookieJar()
        self.loggedIn = False

    def login(self, username=None, password=None, passkey=None):
        config = ConfigParser.ConfigParser()
        config.read('creds.ini')
        username = config.get('CG', 'username')
        password = config.get('CG', 'password')
        data = urllib.urlencode({ "username": username, "password": password})
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.__cookieJar))
        request = urllib2.Request( self.baseURL + "/takelogin.php", data )
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
        rows = soup.find('table', class_='torrenttable').find('tbody').find_all('tr')
        retArray = []
        for r in rows:
            data = {}
            data['Title'] = r.find('a', href=re.compile('details.php\?id=[0-9]+$'))['title']
            data['Size'] = r.find(text=re.compile('[0-9]+\.[0-9]+ [A-Z]B'))
            data['Seeders'] = re.match(r'([0-9]+)', r.find(title=re.compile('[0-9]+ seeders?'))['title']).group(1)
            retArray.append(data)
        return retArray

    def __httpRequest(self, url, data=None):
        if not self.loggedIn:
            print "Not logged in"
            return None
        html = self.__request(self.baseURL + url, data)
        soup = BeautifulSoup(html)
        return soup

    def __request(self, url, data=None):
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.__cookieJar))
        request = urllib2.Request(url, data, headers=self.HttpHeader)
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
