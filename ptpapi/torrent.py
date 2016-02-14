import re
import os
import logging
from urlparse import parse_qs, urlparse

from bs4 import BeautifulSoup as bs4

from config import config
from session import session
from error import PTPAPIException

logger = logging.getLogger(__name__)


class Torrent:
    def __init__(self, ID=None, data=None):
        self.key_finder = {
            'movie_json': [
                'Quality',
                'Source',
                'Container',
                'UploadTime',
                'Codec',
                'Leechers',
                'Seeders',
                'Snatched',
                'ReleaseName',
                'GoldenPopcorn',
                'Checked',
                'RemasterTitle',
                'GroupId',
                'Scene',
                'Resolution',
                'Size'
            ],
            'torrent_json': [
                'Description',
                'Nfo'
            ],
            'movie_html': [
                'Filelist'
            ]
        }

        if data:
            self.data = data
            if 'Id' in data:
                self.ID = data['Id']
            elif 'TorrentId' in data:
                self.ID = data['TorrentId']
            else:
                raise PTPAPIException("Could not find torrent ID in data")
        elif ID:
            self.ID = ID
            self.data = {'Id': ID}
        else:
            raise PTPAPIException("Not enough information to intialize torrent")

    def __repr__(self):
        return "<ptpapi.Torrent ID %s>" % self.ID

    def __str__(self):
        return "<ptpapi.Torrent ID %s>" % self.ID

    def __nonzero__(self):
        return self.ID is not None

    def __getitem__(self, name):
        if name not in self.data or self.data[name] is None:
            for k, v in self.key_finder.iteritems():
                if name in v:
                    getattr(self, "load_%s_data" % k)()
        return self.data[name]

    def __setitem__(self, key, value):
        self.data[key] = value

    def items(self):
        return self.data.items()

    def keys(self):
        return self.data.keys()

    def load_movie_html_data(self):
        if 'GroupId' not in self.data or not self.data['GroupId']:
            movie_url = session.base_get('torrents.php', params={'torrentid': self.ID}).url
            self.data['GroupId'] = parse_qs(urlparse(movie_url).query)['id'][0]
        soup = bs4(session.base_get('torrents.php', params={'id': self.data['GroupId']}).content, "html.parser")
        filediv = soup.find("div", id="files_%s" % self.ID)
        self.data['Filelist'] = {}
        for e in filediv.find("tbody").find_all("tr"):
            bytesize = e("td")[1]("span")[0]['title'].replace(",", "").replace(' bytes', '')
            self.data['Filelist'][e("td")[0].string] = bytesize
        # Check if trumpable
        if soup.find("trumpable_%s" % self.ID):
            self.data['Trumpable'] = [s.get_text() for s in soup.find("trumpable_%s" % self.ID).find('span')]
        else:
            self.data['Trumpable'] = []

    def load_movie_json_data(self):
        logger.debug("Loading Torrent data from movie JSON page.")
        if 'GroupId' not in self.data or not self.data['GroupId']:
            movie_url = session.base_get('torrents.php', params={'torrentid': self.ID}).url
            self.data['GroupId'] = re.search(r'\?id=(\d+)', movie_url).group(1)
        movieData = session.base_get('torrents.php',
                                     params={'torrentid': self.ID,
                                             'id': self.data['GroupId'],
                                             'json': '1'}).json()
        for t in movieData['Torrents']:
            if int(t['Id']) == int(self.ID):
                # Fill in any optional fields
                for key in ['RemasterTitle']:
                    self.data[key] = ''
                self.data.update(t)
                break

    def load_torrent_json_data(self):
        logger.debug("Loading Torrent data from torrent JSON page.")
        if 'GroupId' not in self.data or not self.data['GroupId']:
            movie_url = session.base_get('torrents.php', params={'torrentid': self.ID}).url
            self.data['GroupId'] = re.search(r'\?id=(\d+)', movie_url).group(1)
        self.data.update(session.base_get('torrents.php',
                                          params={'action': 'description',
                                                  'id': self.data['GroupId'],
                                                  'torrentid': self.ID}).json())

    def download(self):
        r = session.base_get("torrents.php",
                             params={'action': 'download',
                                     'id': self.ID})
        self.downloadName = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        return r.content

    def download_to_file(self, dest=None, name=None):
        r = session.base_get("torrents.php",
                             params={'action': 'download',
                                     'id': self.ID})
        if not dest:
            dest = config.get('Main', 'downloadDirectory')
        if not name:
            name = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        with open(os.path.join(dest, name), 'wb') as fh:
            fh.write(r.content)
        return os.path.join(dest, name)
