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
