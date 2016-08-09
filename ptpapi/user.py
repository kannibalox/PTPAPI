"""Represent a user"""
import re

from bs4 import BeautifulSoup as bs4 # pylint: disable=import-error

import api
from session import session
from movie import Movie


class User(object):
    """A primitive class to represent a user"""
    def __init__(self, ID):
        # Requires an ID, as searching by name isn't exact on PTP
        self.ID = ID # pylint: disable=invalid-name

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "<ptpapi.User ID %s>" % self.ID

    def bookmarks(self, search_terms=None):
        """Fetch a list of movies the user has bookmarked

        :rtype: array of Movies"""
        search_terms = search_terms or {}
        search_terms.update({'userid': self.ID})
        req = session.base_get('bookmarks.php', params=search_terms)
        movies = []
        for movie in api.Util.snarf_cover_view_data(req.text):
            movie['Torrents'] = []
            for group in movie['GroupingQualities']:
                for torrent in group['Torrents']:
                    torrent_re = r'&#(\d*);.*title="(.*?)">(.*?) / (.*?) / (.*?) / (.*?)[ <]' # pylint: disable=line-too-long
                    match = re.search(torrent_re, torrent['Title'])
                    torrent['GoldenPopcorn'] = (match.group(1) == '10047') # 10047 = Unicode GP symbol pylint: disable=line-too-long
                    torrent['ReleaseName'] = match.group(2)
                    torrent['Codec'] = match.group(3)
                    torrent['Container'] = match.group(4)
                    torrent['Source'] = match.group(5)
                    torrent['Resolution'] = match.group(6)
                    movie['Torrents'].append(torrent)
            movies.append(Movie(data=movie))
        return movies

    def ratings(self):
        """Fetch a list of rated movies

        :rtype: array of tuples with a Movie and a rating out of 100"""
        soup = bs4(session.base_get(
            'user.php',
            params={'id': self.ID, 'action': 'ratings'}
        ).text, "html.parser")
        ratings = []
        for row in soup.find(id='ratings_table').tbody.find_all('tr'):
            movie_id = re.search(r'id=(\d+)',
                                 row.find(class_='l_movie')['href']).group(1)
            rating = row.find(id='user_rating_%s' % movie_id).text.rstrip('%')
            ratings.append((movie_id, rating))
        return ratings


class CurrentUser(User):
    """Defines some additional methods that only apply to the logged in user."""
    def __init__(self, ID):
        self.ID = ID
        super(CurrentUser, self).__init__(self)
        self.new_messages = 0

    def __parse_new_messages(self, soup):
        """Parse the number of messages from a soup of html"""
        msgs = 0
        if soup.find(class_='alert-bar'):
            for alert in soup.find(class_='alert-bar'):
                match = re.search(r'You have (\d+) new message', alert.text)
                if match:
                    msgs = match.group(1)
        return msgs

    def get_new_messages(self):
        """Update the number of messages"""
        soup = bs4(session.base_get('inbox.php').text, "html.parser")
        self.new_messages = self.__parse_new_messages(soup)
        return self.new_messages

    def inbox(self, page=1):
        """Fetch a list of messages from the user's inbox
        Incidentally update the number of messages"""
        soup = bs4(session.base_get('inbox.php', params={'page': page}).text, "html.parser")

        self.new_messages = self.__parse_new_messages(soup)

        for row in soup.find(id="messageformtable").tbody.find_all('tr'):
            yield {'Subject': row.find_all('td')[1].text.encode('UTF-8').strip(),
                   'Sender': row.find_all('td')[2].text,
                   'Date': row.find_all('td')[3].span['title'],
                   'ID': re.search(r'id=(\d+)', row.find_all('td')[1].a['href']).group(1),
                   'Unread': True if 'inbox-message--unread' in row['class'] else False}

    def inbox_conv(self, conv_id):
        """Get a spefici conversation from the inbox"""
        soup = bs4(session.base_get('inbox.php', params={'action': 'viewconv', 'id': conv_id}).text, "html.parser")
        messages = []
        for msg in soup.find_all('div', id=re.compile('^message'), class_="forum-post"):
            message = {}
            message['Text'] = msg.find('div', class_="forum-post__body").text.strip()
            username = msg.find('strong').find('a', class_="username")
            if username is None:
                message['User'] = 'System'
            else:
                message['User'] = username.text.strip()
            message['Time'] = msg.find('span', class_="time").text.strip()
            messages.append(message)
        return {
            'Subject': soup.find('h2', class_="page__title").text,
            'Message': messages
        }

    def remove_snatched_bookmarks(self):
        """Remove snatched bookmarks"""
        session.base_post("bookmarks.php", data={'action': 'remove_snatched'})

    def remove_seen_bookmarks(self):
        """Remove seen bookmarks"""
        session.base_post("bookmarks.php", data={'action': 'remove_seen'})

    def remove_uploaded_bookmarks(self):
        """Remove uploads bookmarks"""
        session.base_post("bookmarks.php", data={'action': 'remove_uploaded'})

    def hnr_zip(self):
        """Download the zip file of all HnRs"""
        zip_file = session.base_get('snatchlist.php', params={'action': 'hnrzip'})
        if zip_file.headers['Content-Type'] == 'application/zip':
            return zip_file
        else:
            return None
