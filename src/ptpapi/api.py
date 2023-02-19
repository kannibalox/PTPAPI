#!/bin/env python
"""The entrypoint module for access the API"""
import html
import logging
import os
import pickle
import re

import requests

from bs4 import BeautifulSoup as bs4

from ptpapi import util
from ptpapi.config import config
from ptpapi.error import PTPAPIException
from ptpapi.movie import Movie
from ptpapi.session import session
from ptpapi.user import CurrentUser


LOGGER = logging.getLogger(__name__)


def login(kwargs):
    """Simple helper function"""
    return API(**kwargs)


class API:
    """Used for instantiating an object that can access the API"""

    def __init__(
        self, username=None, password=None, passkey=None, api_user=None, api_key=None
    ):
        self.current_user_id = None
        j = None
        self.cookies_file = os.path.expanduser(config.get("Main", "cookiesFile"))
        logger = logging.getLogger(__name__)
        LOGGER.info("Initiating login sequence.")

        if config.has_option("PTP", "ApiUser") and config.has_option("PTP", "ApiKey"):
            pass
        elif (
            config.has_option("PTP", "password")
            and config.has_option("PTP", "username")
            and config.has_option("PTP", "passkey")
        ):
            logger.warning(
                "Using your password/passkey to access the site is deprecated, "
                + "see README.md for instructions on using the new ApiUser/ApiKey."
            )
        else:
            raise PTPAPIException("No credentials found!")

        req = None

        if config.has_option("PTP", "ApiUser") and api_user is None and api_key is None:
            session.headers.update(
                {
                    "ApiUser": config.get("PTP", "ApiUser"),
                    "ApiKey": config.get("PTP", "ApiKey"),
                }
            )
        elif api_user is not None and api_key is not None:
            session.headers.update(
                {
                    "ApiUser": api_user,
                    "ApiKey": api_key,
                }
            )
        elif os.path.isfile(self.cookies_file):
            self.__load_cookies()
            # A really crude test to see if we're logged in
            session.max_redirects = 1
            try:
                req = session.base_get("torrents.php")
                util.raise_for_cloudflare(req.text)
            except requests.exceptions.TooManyRedirects:
                if os.path.isfile(self.cookies_file):
                    os.remove(self.cookies_file)
                session.cookies = requests.cookies.RequestsCookieJar()
            session.max_redirects = 3
        # If we're not using the new method and we don't have a cookie, get one
        if not config.has_option("PTP", "ApiUser") and not os.path.isfile(
            self.cookies_file
        ):
            password = password or config.get("PTP", "password")
            username = username or config.get("PTP", "username")
            passkey = passkey or config.get("PTP", "passkey")
            if not password or not passkey or not username:
                raise PTPAPIException("Not enough info provided to log in.")
            try:
                req = session.base_post(
                    "ajax.php?action=login",
                    data={
                        "username": username,
                        "password": password,
                        "passkey": passkey,
                    },
                )
                j = req.json()
            except ValueError:
                if req.status_code == 200:
                    raise PTPAPIException(
                        "Could not parse returned json data."
                    ) from ValueError
                if req.status_code == 429:
                    LOGGER.critical(req.text.strip())
                req.raise_for_status()
            if j["Result"] == "TfaRequired":
                req = session.base_post(
                    "ajax.php?action=login",
                    data={
                        "username": username,
                        "password": password,
                        "passkey": passkey,
                        "TfaType": "normal",
                        "TfaCode": input("Enter 2FA auth code:"),
                    },
                )
                j = req.json()
            if j["Result"] != "Ok":
                raise PTPAPIException(
                    "Failed to log in. Please check the username, password and passkey. Response: %s"
                    % j
                )
            self.__save_cookie()
            # Get some information that will be useful for later
            req = session.base_get("index.php")
            util.raise_for_cloudflare(req.text)
        LOGGER.info("Login successful.")

    def is_api(self):
        """Helper function to check for the use of ApiUser"""
        return config.has_option("PTP", "ApiKey")

    def logout(self):
        """Forces a logout. In ApiUser mode, essentially a waste of two request tokens."""
        req = session.base_get("index.php")
        auth_key = re.search(r"auth=([0-9a-f]{32})", req.text).group(1)
        os.remove(self.cookies_file)
        return session.base_get("logout.php", params={"auth": auth_key})

    def __save_cookie(self):
        """Save requests' cookies to a file"""
        with open(self.cookies_file, "wb") as fileh:
            LOGGER.debug("Pickling HTTP cookies to %s", self.cookies_file)
            pickle.dump(requests.utils.dict_from_cookiejar(session.cookies), fileh)

    def __load_cookies(self):
        """Reload requests' cookies"""
        with open(self.cookies_file, "rb") as fileh:
            LOGGER.debug("Unpickling HTTP cookies from file %s", self.cookies_file)
            session.cookies = requests.utils.cookiejar_from_dict(pickle.load(fileh))

    def current_user(self):
        """Function to get the current user"""
        # TODO: See if it can be scraped earlier without an extra request
        if self.current_user_id is None:
            req = session.base_get("index.php")
            self.current_user_id = re.search(r"user.php\?id=(\d+)", req.text).group(1)
        return CurrentUser(self.current_user_id)

    def search(self, filters, add_coverview_data=False):
        """Perform a movie search"""
        if "name" in filters:
            filters["searchstr"] = filters["name"]
        filters["json"] = "noredirect"
        ret_array = []
        for movie in session.base_get("torrents.php", params=filters).json()["Movies"]:
            if "Directors" not in movie:
                movie["Directors"] = []
            if "ImdbId" not in movie:
                movie["ImdbId"] = "0"
            movie["Title"] = html.unescape(movie["Title"])
            ret_array.append(Movie(data=movie))
        return ret_array

    # There's probably a better place to put this, but it's not really useful inside the Movie class
    search_coverview_fields = [
        "RtRating",
        "RtUrl",
        "UserRating",
        "TotalSeeders",
        "TotalSnatched",
        "TotalLeechers",
    ]

    def search_coverview(self, filters):
        filters["json"] = 0
        ret_array = []
        if "name" in filters:
            filters["searchstr"] = filters["name"]
        for movie in util.snarf_cover_view_data(
            session.base_get("torrents.php", params=filters).content, key=b"PageData"
        ):
            if "UserRating" not in movie:
                movie["UserRating"] = None
            ret_array.append(Movie(data=movie))
        return ret_array

    def search_single(self, filters):
        """If you know ahead of time that a filter will redirect to a single movie,
        you can use this method to avoid an exception until that behavior is
        fixed upstream."""
        if "name" in filters:
            filters["searchstr"] = filters["name"]
        filters["json"] = "noredirect"
        resp = session.base_get("torrents.php", params=filters)
        movie_id = re.search(r"id=([0-9]+)", resp.url)
        if movie_id is not None:
            return Movie(ID=movie_id.group(1))
        else:
            return None

    def upload_info(self):
        """Scrape as much info as possible from upload.php"""
        data = {}
        soup = bs4(session.base_get("upload.php").content, "html.parser")
        data["announce"] = soup.find_all(
            "input",
            type="text",
            value=re.compile("http://please.passthepopcorn.me:2710/.*/announce"),
        )[0]["value"]
        data["subtitles"] = {}
        label_list = [
            u.find_all("label") for u in soup.find_all(class_="languageselector")
        ]
        labels = [item for sublist in label_list for item in sublist]
        for l in labels:
            data["subtitles"][l["for"].lstrip("subtitle_")] = l.get_text().strip()
        data["remaster_title"] = [
            a.get_text() for a in soup.find(id="remaster_tags").find_all("a")
        ]
        data["resolutions"] = [
            o.get_text() for o in soup.find(id="resolution").find_all("option")
        ]
        data["containers"] = [
            o.get_text() for o in soup.find(id="container").find_all("option")
        ]
        data["sources"] = [
            o.get_text() for o in soup.find(id="source").find_all("option")
        ]
        data["codecs"] = [
            o.get_text() for o in soup.find(id="codec").find_all("option")
        ]
        data["tags"] = [
            o.get_text() for o in soup.find(id="genre_tags").find_all("option")
        ]
        data["categories"] = [
            o.get_text() for o in soup.find(id="categories").find_all("option")
        ]
        data["AntiCsrfToken"] = soup.find("body")["data-anticsrftoken"]
        return data

    def need_for_seed(self, filters=None):
        """List torrents that need seeding"""
        if filters is None:
            filters = {}
        data = util.snarf_cover_view_data(
            session.base_get("needforseed.php", params=filters).content
        )
        torrents = []
        for m in data:
            torrent = m["GroupingQualities"][0]["Torrents"][0]
            torrent["Link"] = (
                config.get("Main", "baseURL")
                + bs4(torrent["Title"], "html.parser").find("a")["href"]
            )
            torrents.append(torrent)
        return torrents

    def contest_leaders(self):
        """Get data on who's winning"""
        LOGGER.debug("Fetching contest leaderboard")
        soup = bs4(session.base_get("contestleaders.php").content, "html.parser")
        ret_array = []
        for cell in (
            soup.find("table", class_="table--panel-like").find("tbody").find_all("tr")
        ):
            ret_array.append(
                (cell.find_all("td")[1].get_text(), cell.find_all("td")[2].get_text())
            )
        return ret_array

    def collage_all(self, coll_id, search_terms={}):
        """Gets all the movies in a collage in one request, only fills torrentid"""
        search_terms["id"] = coll_id
        req = session.base_get("collages.php", params=search_terms)
        soup = bs4(req.content, "html.parser")

        def not_missing_li(tag):
            return tag.has_attr("name") and (tag.name == "li")

        movielist = soup.find(id="collection_movielist").find_all(not_missing_li)
        movies = []
        for page_movie in movielist:
            movieid = page_movie.a["href"].split("id=")[1]
            movies.append(ptpapi.Movie(ID=movieid))
        return movies

    def collage_add(self, coll_id, movieobj):
        """Adds a given movie to a collage, requires password login."""
        search_terms = dict(id=coll_id)
        req = session.base_get("collages.php", params=search_terms)
        soup = bs4(req.content, "html.parser")
        csrf_token = soup.find(id="add_film").find("input")["value"]
        movieobj.load_inferred_data()
        resp = session.base_post(
            "collages.php",
            params=dict(action="add_torrent"),
            data=dict(
                AntiCsrfToken=csrf_token,
                action="add_torrent",
                collageid=coll_id,
                url=movieobj.data["Link"],
            ),
        )
        return resp

    def collage(self, coll_id, search_terms=None):
        """Simplistic representation of a collage, might be split out later"""
        if search_terms is None:
            search_terms = {}
        search_terms["id"] = coll_id
        req = session.base_get("collages.php", params=search_terms)
        movies = []
        for movie in util.snarf_cover_view_data(req.content):
            movie["Torrents"] = []
            for group in movie["GroupingQualities"]:
                movie["Torrents"].extend(group["Torrents"])
            movies.append(Movie(data=movie))
        return movies

    def artist(self, art_id, search_terms=None):
        """Simplistic representation of an artist page, might be split out later"""
        if search_terms is None:
            search_terms = {}
        search_terms["id"] = art_id
        req = session.base_get("artist.php", params=search_terms)
        movies = []
        for movie in util.snarf_cover_view_data(
            req.content, key=b"ungroupedCoverViewJsonData"
        ):
            movie["Torrents"] = []
            for group in movie["GroupingQualities"]:
                movie["Torrents"].extend(group["Torrents"])
            movies.append(Movie(data=movie))
        return movies

    def log(self):
        """Gets the PTP log"""
        soup = bs4(session.base_get("log.php").content, "html.parser")
        ret_array = []
        for message in soup.find("table").find("tbody").find_all("tr"):
            ret_array.append(
                (
                    message.find("span", class_="time")["title"],
                    message.find("span", class_="log__message")
                    .get_text()
                    .lstrip()
                    .encode("UTF-8"),
                )
            )
        return ret_array
