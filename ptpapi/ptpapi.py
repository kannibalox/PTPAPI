#!/bin/env python
import ConfigParser
import re
import os
import json
import pickle
import logging
from datetime import datetime
from time import sleep, time

from bs4 import BeautifulSoup as bs4
import requests

baseURL = 'https://tls.passthepopcorn.me/'
cookiesFile = 'cookies.txt'

logger = logging.getLogger(__name__)

class TokenSession(requests.Session):
    """Allows rate-limiting requests to the site"""
    def __init__(self, tokens, fill_rate):
        """tokens is the total tokens in the bucket. fill_rate is the
        rate in tokens/second that the bucket will be refilled."""
        super(TokenSession, self).__init__()
        self.capacity = float(tokens)
        self._tokens = float(tokens)
        self.fill_rate = float(fill_rate)
        self.timestamp = time()
        
    def consume(self, tokens):
        """Consume tokens from the bucket. Returns True if there were
        sufficient tokens otherwise False."""
        self.get_tokens()
        if tokens <= self.tokens:
            self._tokens -= tokens
            logger.debug("Consuming %i token(s)." % tokens)
        else:
            return False
        return True

    def request(self, *args, **kwargs):
        while not self.consume(1):
            logger.debug("Waiting for token bucket to refill...")
            sleep(1)
        return super(TokenSession, self).request(*args, **kwargs)

    def get_tokens(self):
        if self._tokens < self.capacity:
            now = time()
            delta = self.fill_rate * (now - self.timestamp)
            self._tokens = min(self.capacity, self._tokens + delta)
            self.timestamp = now
        return self._tokens
        
    tokens = property(get_tokens)

# If you change this and get in trouble, don't blame me
logger.debug("Initializing token session")
session = TokenSession(3, 0.5)
session.headers.update({"User-Agent": "Wget/1.13.4"})

def login(**kwargs):
    """Simple helper function"""
    return API(**kwargs)

class PTPAPIException(Exception):
    """A generic exception to designate module-specific errors"""
    pass
    
class Movie:
    """A class representing a movie"""
    def __init__(self, ID=None, data=None):
        self.torrents = []
        self.jsonKeys = ['ImdbId', 'ImdbRating', 'ImdbVoteCount', 'Torrents']
        self.htmlKeys = ['Title', 'Year', 'Cover', 'Tags']
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

    def __getattr__(self, name):
        if name not in self.data:
            if name in self.jsonKeys:
                self.load_json_data()
            elif name in self.htmlKeys:
                self.load_html_data()
        return self.data[name]

    def load_json_data(self, basic=True, overwrite=False):
        self.data.update(session.get(baseURL + "torrents.php",
                                params={'id': self.ID,
                                        'json': '1'}).json())
        self.conv_json_torrents()


    def conv_json_torrents(self):
        if self.data['Torrents']:
            torrents = self.data['Torrents']
            self.data['Torrents'] = []
            for t in torrents:
                self.data['Torrents'].append(Torrent(data=t))

    def load_html_data(self, basic=True, overwrite=False):
        soup = bs4(session.get(baseURL + "torrents.php", params={'id':self.ID}).text)
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
        return 
        for t in self.torrents:
            # Get file list
            filediv = soup.find("div", id="files_%s" % t.ID)
            t.data['Filelist'] = {}
            for e in filediv.find("tbody").find_all("tr"):
                bytesize = e("td")[1]("span")[0]['title'].replace(",","").replace(' bytes', '')
                t.data['Filelist'][e("td")[0].string] = bytesize

class Torrent:
    def __init__(self, ID=None, data=None):
        self.movieJsonKeys = ['Quality', 'Source', 'Container', 'UploadTime', 'Codec', 'Leechers', 'Seeders', 'Snatched', 'ReleaseName', 'GoldenPopcorn', 'Checked', 'RemasterTitle', 'GroupId', 'Scene', 'Resolution', 'Size']
        self.torrentJsonKeys = ['Description', 'Nfo']
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
        
    def __getattr__(self, name):
        if name not in self.data or self.data[name] is None:
            if name in self.movieJsonKeys:
                self.load_movie_json_data()
            if name in self.torrentJsonKeys:
                self.load_torrent_json_data()
        return self.data[name]

    def load_movie_json_data(self):
        logger.debug("Loading Torrent data from movie JSON page.")
        if 'GroupId' not in self.data or not self.data['GroupId']:
            movie_url = session.get(baseURL + 'torrents.php', params={'torrentid': self.ID}).url
            self.data['GroupId'] = re.search(r'\?id=(\d+)', movie_url).group(1)
        movieData = session.get(baseURL + 'torrents.php',
                                params={'torrentid': self.ID,
                                        'id': self.data['GroupId'],
                                        'json':'1'}).json()
        for t in movieData['Torrents']:
            if int(t['Id']) == int(self.ID):
                self.data.update(t)
                break

    def load_torrent_json_data(self):
        logger.debug("Loading Torrent data from torrent JSON page.")
        if 'GroupId' not in self.data or not self.data['GroupId']:
            movie_url = session.get(baseURL + 'torrents.php', params={'torrentid': self.ID}).url
            self.data['GroupId'] = re.search(r'\?id=(\d+)', movie_url).group(1)
        self.data.update(session.get(baseURL + 'torrents.php',
                                     params = {'action': 'description',
                                               'id': self.data['GroupId'],
                                               'torrentid': self.ID }).json())

    def download(self):
        r = session.get(baseURL + "torrents.php",
                        params={'action': 'download',
                                'id': self.ID})
        self.downloadName = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        return r.content

    def download_to_file(self, dest=None, name=None):
        r = session.get(baseURL + "torrents.php",
                        params={'action': 'download',
                                'id': self.ID})
        if not dest:
            dest = os.getcwd()
        if not name:
            name = re.search(r'filename="(.*)"', r.headers['Content-Disposition']).group(1)
        with open(os.path.join(dest, name), 'wb') as fh:
            fh.write(r.content)
        return os.path.join(dest, name)

class User:
    """A primitive class to represent a user"""
    def __init__(self, ID):
        # Requires an ID, as searching by name isn't exact on PTP
        self.ID = ID

    def __repr__(self):
        return "<ptpapi.User ID %s>" % self.ID

    def __str__(self):
        return "<ptpapi.User ID %s>" % self.ID

    def bookmarks(self):
        """Fetch a list of movies the user has bookmarked

        :rtype: array of Movies"""
        r = session.get(baseURL + 'bookmarks.php', params={'id': self.ID})
        movies = []
        for m in util.snarf_cover_view_data(r.text):
            m['Torrents'] = []
            for g in m['GroupingQualities']:
                m['Torrents'].extend(g['Torrents'])
            movies.append(Movie(data=m))
        return movies

    def ratings(self):
        """Fetch a list of rated movies

        :rtype: array of tuples with a Movie and a rating out of 100"""
        soup = bs4(session.get(baseURL + 'user.php', params={'id': self.ID, 'action': 'ratings'}).text)
        ratings = []
        for row in soup.find(id='ratings_table').tbody.find_all('tr'):
            movieID = re.search(r'id=(\d+)', row.find(class_='l_movie')['href']).group(1)
            print movieID
            r = row.find(id='user_rating_%s' % movieID).text.rstrip('%')
            ratings.append((movieID, r))
        return ratings
    

class API:
    def __init__(self, conf=None, username=None, password=None, passkey=None):
        global session
        j = None
        logger.info("Initiating login sequence.")
        if os.path.isfile(cookiesFile):
            self.__load_cookies()
            # A really crude test to see if we're logged in
            session.max_redirects = 1
            try:
                r = session.get(baseURL + 'torrents.php')
            except requests.exceptions.TooManyRedirects:
                os.remove(cookiesFile)
                session.cookies = requests.cookies.RequestsCookieJar()
            session.max_redirects = 3
        if not os.path.isfile(cookiesFile):
            if not password or not passkey or not username:
                raise PTPAPIException("Not enough info provided to log in.")
            try:
                j = session.post(baseURL + 'ajax.php?action=login',
                                 data={"username": username,
                                       "password": password,
                                       "passkey": passkey }).json()
            except ValueError as e:
                raise PTPAPIException("Could not parse returned json data.")
            if j["Result"] != "Ok":
                raise PTPAPIException("Failed to log in. Please check the username, password and passkey. Response: %s" % j)
            self.__save_cookie()
            # Get some information that will be useful for later
            r = session.get(baseURL + 'index.php')
        logger.info("Login successful.")
        self.current_user_id = re.search(r'user.php\?id=(\d+)', r.text).group(1)
        self.auth_key = re.search(r'auth=([0-9a-f]{32})', r.text).group(1)

    def logout(self):
        """Forces a logout."""
        os.remove(cookiesFile)
        return session.get(baseURL + 'logout.php', params={'auth': self.auth_key})

    def __save_cookie(self):
        with open(cookiesFile, 'w') as fh:
            logger.debug("Pickling HTTP cookies to %s" % cookiesFile)
            pickle.dump(requests.utils.dict_from_cookiejar(session.cookies), fh)

    def __load_cookies(self):
        global session
        with open(cookiesFile) as fh:
            logger.debug("Unpickling HTTP cookies from file %s" % cookiesFile)
            session.cookies = requests.utils.cookiejar_from_dict(pickle.load(fh))

    def current_user(self):
        return User(self.current_user_id)

    def hnr_zip(self):
        return session.get(baseURL + 'snatchlist.php', params={'action':'hnrzip'})
        
    def search(self, filters):
        if 'name' in filters:
            filters['searchstr'] = filters['name']
        filters['json'] = 'noredirect'
        return [Movie(data=m) for m in session.get(baseURL + 'torrents.php', params=filters).json()['Movies']]

    def remove_snatched_bookmarks(self):
        session.post(baseURL + "bookmarks.php", data={'action': 'remove_snatched'})

    def remove_seen_bookmarks(self):
        session.post(baseURL + "bookmarks.php", data={'action': 'remove_seen'})

    def remove_uploaded_bookmarks(self):
        session.post(baseURL + "bookmarks.php", data={'action': 'remove_uploaded'})

    def need_for_seed(self):
        data = util.snarf_cover_view_data(session.get(baseURL + "needforseed.php").content)
        return [t['GroupingQualities'][0]['Torrents'][0] for t in data]

class Collection(object):
    def __init__(self, ID):
        self.ID = ID

def best_match(movie, profile, allow_dead=False):
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
        matches = movie.Torrents
        filter_dict = {
            'gp': (lambda t: t.GoldenPopcorn),
            'scene': (lambda t: t.Scene),
            '576p': (lambda t: t.Resolution == '576p'),
            '480p': (lambda t: t.Resolution == '480p'),
            '720p': (lambda t: t.Resolution == '720p'),
            '1080p': (lambda t: t.Resolution == '1080p'),
            'HD': (lambda t: t.Quality == 'High Definition'),
            'SD': (lambda t: t.Quality == 'Standard Definition'),
            'Remux': (lambda t: 'remux' in t.RemasterTitle.lower()),
            'x264': (lambda t: t.Codec == 'x264')
        }
        for (name, func) in filter_dict.items():
            if name.lower() in p:
                logger.debug("Filtering movies by parameter %s" % name)
                matches = [t for t in matches if func(t)]
        sort_dict = {
            'most recent': (True, (lambda t: datetime.strptime(t.UploadTime, "%Y-%m-%d %H:%M:%S"))),
            'smallest': (False, (lambda t: t.Size)),
            'seeded': (True, (lambda t: t.Seeders)),
            'largest': (True, (lambda t: t.Size)),
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
    logger.info("Could not find best match for movie %s" % movie.ID)
    return None

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
                 
                
