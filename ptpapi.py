#!/bin/env python
from StringIO import StringIO
from bs4 import BeautifulSoup
import re
import urllib
import urllib2
import cookielib
import argparse
import json
import ConfigParser

class PTPAPI:
    HttpHeader = { "User-Agent": "Wget/1.13.4" }

    def __init__(self):
        self.loggedIn = False
        self.baseURL = "https://tls.passthepopcorn.me"
        self.__cookieJar = cookielib.CookieJar()

    def login(self, username, password, passkey):
        """Log into PTP"""
        data = urllib.urlencode({ "username": username, "password": password, "passkey": passkey })
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.__cookieJar))
        request = urllib2.Request(self.baseURL + '/ajax.php?action=login', data, PTPAPI.HttpHeader)
        response = opener.open(request).read()
        jsonResponse = json.loads(response)
        if jsonResponse["Result"] != "Ok":
            raise PTPAPIException("Failed to log in. Please check the username, password and passkey. Response: %s" % jsonResponse)
        self.loggedIn = True

    def logout(self):
        """Logs out the session.

        Not necessary, but keeps your session list clean"""
        if self.loggedIn:
            authkey = self.__jsonRequest('/torrents.php?json=noredirect')['AuthKey']
            self.__request(self.baseURL + '/logout.php?auth=%s' % authkey)
            self.loggedIn = False

    def search(self, search_args):
        """Search for torrents by arbitrary fields"""
        search_string = urllib.urlencode(search_args.items())
        json = self.__jsonRequest("/torrents.php?%s" % (search_string + "&json=noredirect"))
        return json

    def threadPage(self, threadID, page=None):
        """Gets the specified page for a thread (the last page by default)"""
        if not page or page <= 0:
            soup = self.__httpRequest("/forums.php?action=viewthread&threadid=%s" % (threadID))
            page = re.search(r"page=(\d+)", soup.find("a", class_="pagination__link pagination__link--last")['href']).group(1)
        soup = self.__httpRequest("/forums.php?action=viewthread&threadid=%s&page=%s" % (threadID, page))
        return soup

    def unreadPostsInThread(self, threadID):
        """Returns a list of unread posts as divs"""
        soup = self.threadPage(threadID)
        return BeautifulSoup(soup.find_all("div", class_="forum-post--unread"))

    def siteStats(self):
        """Get the stats for the entire site"""
        stats = {}
        soup = self.__httpRequest("/index.php")
        # Massage each of the stat sections, there's probably a cleaner way to do this
        statdiv = soup.find("div", {'id': 'commstats'})
        remove_re = re.compile(r"[\(\[].*[\)\]]")
        # There is a lot of cleaning going on here, which should probably
        ## be broken out into something cleaner
        for li in statdiv("li"):
            stat = li.get_text(strip=True)
            key = remove_re.sub('', stat.split(':')[0].replace(' ', ''))
            if key:
                value = remove_re.sub('', stat.split(':')[1].replace(' ', '')).replace('z', '')
                stats[key] = value
        statdiv = soup.find("div", {'id': 'libstats'})
        for li in statdiv("li"):
            stat = li.get_text(strip=True)
            key = remove_re.sub('', stat.split(':')[0].replace(' ', ''))
            if key:
                if key == 'Requests':
                    match = re.search(r"\(.*\%\)", stat.split(':')[1])
                    if match:
                        stats['RequestsPercentFilled'] = match.group(1)
                value = remove_re.sub('', stat.split(':')[1].replace(' ', '')).replace('z', '')
                stats[key] = value
        return stats

    def userStats(self, userID):
        """Get all available stats for a user"""
        soup = self.__httpRequest("/user.php?id=%s" % (userID))
        userData = {}
        panels = ['Stats', 'Community', 'Personal']
        for p in panels:
            # Find each unordered list of stats
            statList = soup.find(text=p).parent.parent.next_sibling.next_sibling.find("ul")
            for stat in statList.find_all("li"):
                name, value = self.__parseStat(stat)
                userData[name] = value
        # Make sure these don't get exposed by accident
        del userData['Email']
        del userData['Clients']
        del userData['Passkey']
        return userData

    def __parseStat(self, listElement):
        """Takes a <li> soup element and returns a tuple of the key and the value"""
        # Use the absolute date instead of the relative one
        if listElement.find("span", class_="time"):
            name = listElement.text.split(':')[0]
            value = listElement.find("span")['title']
        else:
            name, value = listElement.text.split(':')[0:2]
        # Strip out unneeded text
        name = name.strip().title().replace(' ', '')
        value = value.strip('\n').replace("[View]", "").replace("[Download]", "").strip()
        # If it's a number, remove all thousands separators
        if re.search(r'^[0-9,]*$', str(value)):
            value = value.replace(',', '')
        return (name, value)

    def findTorrentLinks(self, soup):
        "Given a soup, scrape all links to torrents (not torrent information)"
        IDs = []
        for anchor in soup.find_all('a'):
            match = re.search(r"torrentid=(\d+)", anchor['href'])
            if match != None:
                IDs.append(match.group(1))
        return IDs

    def movieInformation(self, movieID=None, torrentID=None):
        """Get information about a movie, either by group ID or torrent ID"""
        if not movieID and not torrentID:
            raise PTPAPIException("Must include either movieID or torrentID")
        # The torrent ID is really only used to get the movie ID
        # It uses an extra http call, but that shouldn't be a big deal
        if torrentID and not movieID:
            url = "/torrents.php?torrentid=%s" % torrentID
            self.__request(self.baseURL + url).get(url)
            # The args variable is set by the __request call
            movieID = re.search(r'(\d+)$', args.url).group(1)
        data = {}
        # We only need the http request to get the byte size right now
        soup = self.__httpRequest("/torrents.php?id=%s" % movieID)
        data = self.__jsonRequest("/torrents.php?id=%s&json=1" % movieID)
        for index, t in enumerate(data['Torrents']):
            data['Torrents'][index]['Filelist'] = {}
            fileDiv = soup.find("div", id="files_%s" % t['Id'])
            for e in fileDiv.find("tbody").find_all("tr"):
                bytesize = e("td")[1]("span")[0]['title'].replace(",","").replace(' bytes', '')
                data['Torrents'][index]['Filelist'][e("td")[0].string] = bytesize
        return data

    def torrentInformation(self, torrentID):
        """Get all information about a specific torrent by ID"""
        data = {}
        data['Filelist'] = {}
        soup = self.__httpRequest("/torrents.php?torrentid=%s" % torrentID)
        fileDiv = soup.find("div", id="files_%s" % torrentID)
        print fileDiv.find("tbody")
        for e in fileDiv.find("tbody").find_all("tr"):
            bytesize = e("td")[1]("span")[0]['title'].replace(",","").replace(' bytes', '')
            data['Filelist'][e("td")[0].string] = bytesize
        print fileDiv.find_all('tbody>tr')
        soup.find_all("tr", id="group_torrent_header_%s" % torrentID)[0]
        return data

    def downloadTorrent(self, tID):
        """Download the actual torrent file

        Returns a tuple of the filename, and the file socket"""
        t = self.__request(self.baseURL + "/torrents.php?action=download&id=%i" % int(tID))
        if t.info().has_key('Content-Disposition'):
            localName = t.info()['Content-Disposition'].split('filename=')[1]
            if localName[0] == '"' or localName[0] == "'":
                localName = localName[1:-1]
        return (localName, t)

    def __httpRequest(self, url, data=None):
        """Internal function to make an http request
        
        Returns a bs4 soup"""
        if not self.loggedIn:
            print "Not logged in"
            return None
        html = self.__request(self.baseURL + url, data)
        soup = BeautifulSoup(html)
        return soup

    def __request(self, url, data=None):
        """Returns a socket file"""
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.__cookieJar))
        request = urllib2.Request(url, data, headers=self.HttpHeader)
        return opener.open(request)

    def __jsonRequest(self, url, data=None):
        """Internal function to make an json request

        Returns a dictionary"""
        if not self.loggedIn:
            print "Not logged in"
            return None
        return json.loads(self.__request(self.baseURL + url, data).read())

class PTPAPIException(Exception):
    pass
