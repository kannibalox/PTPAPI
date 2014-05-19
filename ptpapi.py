#!/usr/bin/python
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
        self.baseURL = "https://tls.passthepopcorn.me"
        self.__cookieJar = cookielib.CookieJar()
        self.loggedIn = False

    def login(self, username=None, password=None, passkey=None):
        config = ConfigParser.ConfigParser()
        config.read('creds.ini')
        username = config.get('PTP', 'username')
        password = config.get('PTP', 'password')
        passkey = config.get('PTP', 'passkey')
        data = urllib.urlencode({ "username": username, "password": password, "passkey": passkey })
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.__cookieJar))
        request = urllib2.Request(self.baseURL + '/ajax.php?action=login', data, PTPAPI.HttpHeader)
        response = opener.open(request).read()
        jsonResponse = json.loads(response)
        if jsonResponse["Result"] != "Ok":
            raise PTPAPIException("Failed to log in. Please check the username, password and passkey. Response: %s" % jsonResponse)
        self.loggedIn = True

    def search(self, search_args):
        search_string = '&'.join([ "%s=%s" % (key, value) for (key, value) in search_args.items() ])
        json = self.__jsonRequest("/torrents.php?%s" % (search_string + "&json=noredirect"))
        return json

    def threadPage(self, threadID, page=None):
        if not page or page <= 0:
            soup = self.__httpRequest("/forums.php?action=viewthread&threadid=%s" % (threadID))
            page = re.search(r"page=(\d+)", soup.find("a", class_="pagination__link pagination__link--last")['href']).group(1)
        soup = self.__httpRequest("/forums.php?action=viewthread&threadid=%s&page=%s" % (threadID, page))
        return soup

    def unreadPostsInThread(self, threadID):
        soup = self.threadPage(threadID)
        return BeautifulSoup(soup.find_all("div", class_="forum-post--unread"))

    def siteStats(self):
        stats = {}
        soup = self.__httpRequest("/index.php")
        statdiv = soup.find("div", {'id': 'commstats'})
        remove_re = re.compile(r"[\(\[].*[\)\]]")
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
        soup = self.__httpRequest("/user.php?id=%s" % (userID))
        userData = {}
        statList = soup.find(text="Stats").parent.parent.next_sibling.next_sibling.find("ul")
        for stat in statList.find_all("li"):
            print str(stat)
            if stat.find("span", _class="time"):
                name = stat.text.split(':')[0]
                value = stat.span.title
            else:
                name, value = stat.text.split(':')[0:2]
            name = name.strip(' ')
            value = value.strip('\n').replace("[View]", "").strip()
            userData[name] = value
        print userData

    def findTorrentLinks(self, soup):
        IDs = []
        for anchor in soup.find_all('a'):
            match = re.search(r"torrentid=(\d+)", anchor['href'])
            if match != None:
                IDs.append(match.group(1))
        return IDs

    def torrentInformation(self, torrentID):
        data = {}
        soup = self.__htmlRequest("%s/torrents.php?torrentid=%s")
        soup.find_all("tr", id="group_torrent_header_%s" % torrentID)[0]
        

    def downloadTorrent(self, tID):
        t = self.__request(self.baseURL + "/torrents.php?action=download&id=%i" % int(tID))
        if t.info().has_key('Content-Disposition'):
            localName = t.info()['Content-Disposition'].split('filename=')[1]
            if localName[0] == '"' or localName[0] == "'":
                localName = localName[1:-1]
        return (localName, t)

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
        return opener.open(request)

    def __jsonRequest(self, url, data=None):
        if not self.loggedIn:
            print "Not logged in"
            return None
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.__cookieJar))
        request = urllib2.Request(self.baseURL + url, data, headers=self.HttpHeader)
        response = opener.open(request).read()
        return json.loads(response)

class PTPAPIException(Exception):
    pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", '--config', help="The configuration file to use")
    parser.parse_args()
    ptp = PTPAPI()
    ptp.login()
    print ptp.search({'searchstr': 'tt0111512'})
