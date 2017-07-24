import re

import humanize
from bs4 import BeautifulSoup

from ptpapi.config import config
from ptpapi.session import session
from ptpapi.sites.base import BaseSiteAPI

class CGAPI(BaseSiteAPI):
    HttpHeader = {"User-Agent": "Wget/1.13.4"}

    def __init__(self):
        self.baseURL = "https://cinemageddon.net"
        super(CGAPI, self).__init__()

    def login(self, username=None, password=None, passkey=None):
        password = (password or config.get('CG', 'password'))
        username = (username or config.get('CG', 'username'))
        response = session.post(self.baseURL + "/takelogin.php",
                                data={"username": username,
                                      "password": password})
        response.raise_for_status()
        if response.text.find('action="takelogin.php"') != -1:
            raise CGAPIException("Failed to log in")

    def search(self, search_args):
        search_string = '&'.join(["%s=%s" % (key, value) for (key, value) in search_args.items()])
        soup = self.__httpRequest('/browse.php?%s' % search_string)
        return self.getTorrentListInfo(soup)

    def find_ptp_movie(self, movie):
        return self.search({'search': 'tt{0}'.format(movie['ImdbId'])})

    def bytes_to_site_size(self, byte_num):
        humanized = humanize.naturalsize(byte_num, format='%.2f', binary=True)
        if 'KiB' in humanized:
            humanized = humanize.naturalsize(byte_num, format='%d', binary=True)
        return humanized


    def getTorrentListInfo(self, soup):
        if not soup.find('table', class_='torrenttable'):
            return []
        rows = soup.find('table', class_='torrenttable').find('tbody').find_all('tr')
        retArray = []
        for r in rows:
            data = {}
            data['Title'] = r.find('a', href=re.compile(r'details.php\?id=[0-9]+$'))['title']
            data['BinaryHumanSize'] = r.find(text=re.compile(r'[0-9]+\.[0-9]+ [kA-Z]B')).replace('B', 'iB').replace('k', 'K')
            data['Seeders'] = re.match(r'([0-9]+)', r.find(title=re.compile('[0-9]+ seeders?'))['title']).group(1)
            data['ID'] = re.match(r'details.php\?id=([0-9]+)$', r.find('a', href=re.compile(r'details.php\?id=[0-9]+$'))['href']).group(1)
            retArray.append(data)
        return retArray

    def download_torrent(self, tID, name=None):
        r = session.get(self.baseURL + '/download.php', params={'id': tID})
        if not name:
            name = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        with open(name.replace('/', '_'), 'wb') as fh:
            fh.write(r.content)

    def __httpRequest(self, url, data=None):
        html = self.__request(self.baseURL + url, data)
        soup = BeautifulSoup(html, "html5lib")
        return soup

    def __request(self, url, data=None):
        return session.get(url, data=data).text

    def __jsonRequest(self, url, data=None):
        return session.get(url, data=data).json()


class CGAPIException(Exception):
    pass

if __name__ == '__main__':
    cg = CGAPI()
    cg.login()
    print cg.search({'search': 'tt0054650'})
