import re

from bs4 import BeautifulSoup as bs4

import api
from session import session
from movie import Movie


class User(object):
    """A primitive class to represent a user"""
    def __init__(self, ID):
        # Requires an ID, as searching by name isn't exact on PTP
        self.ID = ID

    def __repr__(self):
        return "<ptpapi.User ID %s>" % self.ID

    def __str__(self):
        return "<ptpapi.User ID %s>" % self.ID

    def bookmarks(self, search_terms={}):
        """Fetch a list of movies the user has bookmarked

        :rtype: array of Movies"""
        search_terms.update({'userid': self.ID})
        r = session.base_get('bookmarks.php', params=search_terms)
        movies = []
        for m in api.util.snarf_cover_view_data(r.text):
            m['Torrents'] = []
            for g in m['GroupingQualities']:
                for torrent in g['Torrents']:
                    match = re.search('&#(\d*);.*title="(.*?)">(.*?) / (.*?) / (.*?) / (.*?)[ <]', torrent['Title'])
                    torrent['GoldenPopcorn'] = (match.group(1) == '10047')  # 10047 = Unicode GP symbol
                    torrent['ReleaseName'] = match.group(2)
                    torrent['Codec'] = match.group(3)
                    torrent['Container'] = match.group(4)
                    torrent['Source'] = match.group(5)
                    torrent['Resolution'] = match.group(6)
                    print torrent
                    m['Torrents'].append(torrent)
            movies.append(Movie(data=m))
        return movies

    def ratings(self):
        """Fetch a list of rated movies

        :rtype: array of tuples with a Movie and a rating out of 100"""
        soup = bs4(session.base_get('user.php', params={'id': self.ID, 'action': 'ratings'}).text, "html.parser")
        ratings = []
        for row in soup.find(id='ratings_table').tbody.find_all('tr'):
            movieID = re.search(r'id=(\d+)', row.find(class_='l_movie')['href']).group(1)
            r = row.find(id='user_rating_%s' % movieID).text.rstrip('%')
            ratings.append((movieID, r))
        return ratings


class CurrentUser(User):
    """Defines some additional methods that only apply to the logged in user."""
    def __init__(self, ID):
        super(CurrentUser, self).__init__(self)
        self.num_messages = 0

    def get_num_messages(self):
        m = 0
        soup = bs4(session.base_get('inbox.php').text, "html.parser")
        for alert in soup.find(class_='alert-bar'):
            match = re.search(r'You have (\d+) new message', alert.text)
            if match:
                m = match.group(1)
        self.num_messages = m
        return m

    def inbox(self, page=1):
        soup = bs4(session.base_get('inbox.php', params={'page': page}).text, "html.parser")

        # Update the number of messages
        m = 0
        for alert in soup.find(class_='alert-bar'):
            match = re.search(r'You have (\d+) new message', alert.text)
            if match:
                m = match.group(1)
        self.num_messages = m

        for row in soup.find(id="messageformtable").tbody.find_all('tr'):
            yield {'Subject': row.find_all('td')[1].text.encode('UTF-8').strip(),
                   'Sender': row.find_all('td')[2].text,
                   'Date': row.find_all('td')[3].span['title'],
                   'ID': re.search(r'id=(\d+)', row.find_all('td')[1].a['href']).group(1),
                   'Unread': True if 'inbox-message--unread' in row['class'] else False}

    def inbox_conv(self, conv_id):
        soup = bs4(session.base_get('inbox.php', params={'action': 'viewconv', 'id': conv_id}).text, "html.parser")
        messages = []
        for m in soup.find_all('div', id=re.compile('^message'), class_="forum-post"):
            message = {}
            message['Text'] = m.find('div', class_="forum-post__body").text.strip()
            username = m.find('strong').find('a', class_="username")
            if username is None:
                message['User'] = 'System'
            else:
                message['User'] = username.text.strip()
            message['Time'] = m.find('span', class_="time").text.strip()
            messages.append(message)
        return {
            'Subject': soup.find('h2', class_="page__title").text,
            'Message': messages
        }

    def remove_snatched_bookmarks(self):
        session.base_post("bookmarks.php", data={'action': 'remove_snatched'})

    def remove_seen_bookmarks(self):
        session.base_post("bookmarks.php", data={'action': 'remove_seen'})

    def remove_uploaded_bookmarks(self):
        session.base_post("bookmarks.php", data={'action': 'remove_uploaded'})

    def hnr_zip(self):
        z = session.base_get('snatchlist.php', params={'action': 'hnrzip'})
        if z.headers['Content-Type'] == 'application/zip':
            return z
        else:
            return None
