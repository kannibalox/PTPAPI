import re
import logging
import os.path
from datetime import datetime

from bs4 import BeautifulSoup as bs4

from session import session
from torrent import Torrent
from error import PTPAPIException

logger = logging.getLogger(__name__)


class Movie:
    """A class representing a movie"""
    def __init__(self, ID=None, data=None):
        self.torrents = []
        self.jsonKeys = ['ImdbId', 'ImdbRating', 'ImdbVoteCount', 'Torrents']
        self.htmlKeys = ['Title', 'Year', 'Cover', 'Tags']
        self.key_finder = {
            'json': [
                'ImdbId',
                'ImdbRating',
                'ImdbVoteCount',
                'Torrents'
            ],
            'html': [
                'Title',
                'Year',
                'Cover',
                'Tags'
            ]
        }

        if data:
            self.data = data
            self.conv_json_torrents()
            self.ID = data['GroupId']
        elif ID:
            self.ID = ID
            self.data = {}
        else:
            raise PTPAPIException("Could not load necessary data for Movie class")

    def __repr__(self):
        return "<ptpapi.Movie ID %s>" % self.ID

    def __str__(self):
        return "<ptpapi.Movie ID %s>" % self.ID

    def __getitem__(self, name):
        if name not in self.data or self.data[name] is None:
            for k, v in self.key_finder.iteritems():
                if name in v:
                    getattr(self, "load_%s_data" % k)()
        return self.data[name]

    def load_json_data(self, basic=True, overwrite=False):
        self.data.update(session.base_get("torrents.php",
                                          params={'id': self.ID,
                                                  'json': '1'}).json())
        self.conv_json_torrents()

    def conv_json_torrents(self):
        if self.data['Torrents']:
            torrents = self.data['Torrents']
            self.data['Torrents'] = [Torrent(data=t) for t in torrents]

    def load_html_data(self, basic=True, overwrite=False):
        soup = bs4(session.base_get("torrents.php", params={'id': self.ID}).text, "html.parser")
        self.data['Cover'] = soup.find('img', class_='sidebar-cover-image')['src']
        # Title and Year
        match = re.match(r'(.*) \[(\d{4})\]', soup.find('h2', class_='page__title').encode_contents())
        self.data['Title'] = match.group(1)
        self.data['Year'] = match.group(2)
        # Genre tags
        self.data['Tags'] = []
        for tagbox in soup.find_all('div', class_="box_tags"):
            for t in tagbox.find_all("li"):
                self.data['Tags'].append(t.find('a').string)
        # File list & trumpability
        for t in self.data['Torrents']:
            # Get file list
            filediv = soup.find("div", id="files_%s" % t.ID)
            t.data['Filelist'] = {}
            basepath = re.match(r'\/(.*)\/', filediv.find("thead").find_all("div")[1].string).group(1)
            for e in filediv.find("tbody").find_all("tr"):
                bytesize = e("td")[1]("span")[0]['title'].replace(",", "").replace(' bytes', '')
                filepath = os.path.join(basepath, e("td")[0].string)
                t.data['Filelist'][filepath] = bytesize
            # Check if trumpable
            if soup.find(id="trumpable_%s" % t.ID):
                t.data['Trumpable'] = [s.get_text() for s in soup.find(id="trumpable_%s" % t.ID).find_all('span')]
            else:
                t.data['Trumpable'] = []

    def best_match(self, profile, allow_dead=False):
        """A function to pull the best match of a movie, based on a human-readable filter

        :param movie: a :py:class:`Movie` object
        :param profile: a filter string
        :param allow_dead: Allow dead torrents to be returned
        :type allow_dead: Boolean
        :rtype: The best matching movie, or None"""
        # We're going to emulate what.cd's collector option
        profiles = profile.lower().split(',')
        current_sort = None
        for p in profiles:
            logger.debug("Attempting to match movie to profile: %s" % p)
            matches = self.data['Torrents']
            filter_dict = {
                'gp': (lambda t: t['GoldenPopcorn']),
                'scene': (lambda t: t['Scene']),
                '576p': (lambda t: t['Resolution'] == '576p'),
                '480p': (lambda t: t['Resolution'] == '480p'),
                '720p': (lambda t: t['Resolution'] == '720p'),
                '1080p': (lambda t: t['Resolution'] == '1080p'),
                'HD': (lambda t: t['Quality'] == 'High Definition'),
                'SD': (lambda t: t['Quality'] == 'Standard Definition'),
                'remux': (lambda t: 'remux' in t['RemasterTitle'].lower()),
                'x264': (lambda t: t['Codec'] == 'x264')
            }
            for (name, func) in filter_dict.items():
                if name.lower() in p:
                    logger.debug("Filtering movies by parameter %s" % name)
                    matches = [t for t in matches if func(t)]
                sort_dict = {
                    'most recent': (True, (lambda t: datetime.strptime(t['UploadTime'], "%Y-%m-%d %H:%M:%S"))),
                    'smallest': (False, (lambda t: t['Size'])),
                    'seeded': (True, (lambda t: t['Seeders'])),
                    'largest': (True, (lambda t: t['Size'])),
                }
            for name, (rev, sort) in sort_dict.items():
                if name in p:
                    logger.debug("Sorting by parameter %s" % name)
                    current_sort = name
            if len(matches) == 1:
                return matches[0]
            elif len(matches) > 1 and current_sort:
                (rev, sort) = sort_dict[current_sort]
                return sorted(matches, key=sort, reverse=rev)[0]
            logger.debug("Could not find match for profile: %s" % p)
        logger.info("Could not find best match for movie %s" % self.ID)
        return None
