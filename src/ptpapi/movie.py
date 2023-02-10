"""Represents a movie"""
import logging
import operator
import os.path
import re

from datetime import datetime

from bs4 import BeautifulSoup as bs4  # pylint: disable=import-error

from ptpapi import torrent
from ptpapi.error import PTPAPIException
from ptpapi.session import session
from ptpapi.util import human_to_bytes


LOGGER = logging.getLogger(__name__)


class Movie:
    """A class representing a movie"""

    def __init__(self, ID=None, data=None):
        self.torrents = []
        self.key_finder = {
            "json": ["ImdbId", "ImdbRating", "ImdbVoteCount", "Torrents", "CoverImage", "Name"],
            "html": [
                "Title",
                "Year",
                "Cover",
                "Tags",
                "Directors",
                "PtpRating",
                "PtpVoteCount",
                "UserRating",
                "Seen",
                "Snatched",
            ],
            "inferred": ["Link", "Id", "GroupId"],
        }

        if data:
            self.data = data
            self.conv_json_torrents()
            self.ID = data["GroupId"]  # pylint: disable=invalid-name
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
            for key, val in self.key_finder.items():
                if name in val:
                    getattr(self, "load_%s_data" % key)()
        return self.data[name]

    def items(self):
        """Passthru function for underlying dict"""
        return self.data.items()

    def update(self, obj):
        for k, v in obj.items():
            self.data[k] = v

    def __setitem__(self, key, value):
        self.data[key] = value

    def load_inferred_data(self):
        self.data["Id"] = self.ID
        self.data["GroupId"] = self.ID
        self.data["Link"] = "https://passthepopcorn.me/torrents.php?id=" + self.ID

    def load_json_data(self):
        """Load movie JSON data"""
        self.data.update(
            session.base_get("torrents.php", params={"id": self.ID, "json": "1"}).json()
        )
        if "ImdbId" not in self.data:
            self.data["ImdbId"] = ""
        self.conv_json_torrents()

    def conv_json_torrents(self):
        """Util function to normalize data"""
        if self.data["Torrents"]:
            torrents = self.data["Torrents"]
            for t in torrents:
                if "RemasterTitle" not in t:
                    t["RemasterTitle"] = ""
            self.data["Torrents"] = [torrent.Torrent(data=t) for t in torrents]

    def load_html_data(self):
        """Scrape all data from a movie's HTML page"""
        soup = bs4(
            session.base_get("torrents.php", params={"id": self.ID, "json": 0}).text,
            "html.parser",
        )
        self.data["Cover"] = soup.find("img", class_="sidebar-cover-image")["src"]
        # Title and Year
        match = re.match(
            rb"(.*)(:? \[(\d{4})\])?",
            soup.find("h2", class_="page__title").encode_contents(),
        )
        self.data["Title"] = match.group(1)
        self.data["Year"] = "0" if match.group(2) is None else match.group(2)
        # Genre tags
        self.data["Tags"] = []
        for tagbox in soup.find_all("div", class_="box_tags"):
            for tag in tagbox.find_all("li"):
                self.data["Tags"].append(str(tag.find("a").string))
        # Directors
        self.data["Directors"] = []
        for director in soup.find("h2", class_="page__title").find_all(
            "a", class_="artist-info-link"
        ):
            self.data["Directors"].append({"Name": director.string.strip()})
        # Ratings
        rating = soup.find(id="ptp_rating_td")
        self.data["PtpRating"] = rating.find(id="user_rating").text.strip("%")
        self.data["PtpRatingCount"] = re.sub(
            r"\D", "", rating.find(id="user_total").text
        )
        your_rating = rating.find(id="ptp_your_rating").text
        if "?" in your_rating:
            self.data["UserRating"] = None
            self.data["Seen"] = False
        elif re.sub(r"\D", "", your_rating) == "":
            self.data["UserRating"] = None
            self.data["Seen"] = True
        else:
            self.data["UserRating"] = re.sub(r"\D", "", your_rating)
            self.data["Seen"] = True
        # Have we snatched this
        self.data["Snatched"] = False
        if soup.find(class_="torrent-info-link--user-snatched") or soup.find(
            class_="torrent-info-link--user-seeding"
        ):
            self.data["Snatched"] = True

        # File list & trumpability for torrents
        for tor in self["Torrents"]:
            # Get file list
            filediv = soup.find("div", id="files_%s" % tor.ID)
            tor.data["Filelist"] = {}
            basepath = re.match(
                r"\/(.*)\/", filediv.find("thead").find_all("div")[1].get_text()
            ).group(1)
            for elem in filediv.find("tbody").find_all("tr"):
                try:
                    bytesize = (
                        elem("td")[1]("span")[0]["title"]
                        .replace(",", "")
                        .replace(" bytes", "")
                    )
                except IndexError:
                    LOGGER.error(
                        "Could not parse site for filesize, possibly check for bad filenames: https://passthepopcorn.me/torrents.php?torrentid=%s",
                        tor.ID,
                    )
                    continue
                filepath = os.path.join(basepath, elem("td")[0].string)
                tor.data["Filelist"][filepath] = bytesize
            # Check if trumpable
            if soup.find(id="trumpable_%s" % tor.ID):
                tor.data["Trumpable"] = [
                    s.get_text()
                    for s in soup.find(id="trumpable_%s" % tor.ID).find_all("span")
                ]
            else:
                tor.data["Trumpable"] = []

    def best_match(self, profile):
        """A function to pull the best match of a movie, based on a human-readable filter

        :param profile: a filter string
        :rtype: The best matching movie, or None"""
        # We're going to emulate what.cd's collector option
        profiles = profile.lower().split(",")
        current_sort = None
        if "Torrents" not in self.data:
            self.load_json_data()
        for subprofile in profiles:
            LOGGER.debug("Attempting to match movie to profile '%s'", subprofile)
            matches = self.data["Torrents"]
            simple_filter_dict = {
                "gp": (lambda t, _: t["GoldenPopcorn"]),
                "scene": (lambda t, _: t["Scene"]),
                "576p": (lambda t, _: t["Resolution"] == "576p"),
                "480p": (lambda t, _: t["Resolution"] == "480p"),
                "720p": (lambda t, _: t["Resolution"] == "720p"),
                "1080p": (lambda t, _: t["Resolution"] == "1080p"),
                "HD": (lambda t, _: t["Quality"] == "High Definition"),
                "SD": (lambda t, _: t["Quality"] == "Standard Definition"),
                "not-remux": (lambda t, _: "remux" not in t["RemasterTitle"].lower()),
                "remux": (lambda t, _: "remux" in t["RemasterTitle"].lower()),
                "x264": (lambda t, _: t["Codec"] == "x264"),
                "xvid": (lambda t, _: t["Codec"] == "XviD"),
                "seeded": (lambda t, _: int(t["Seeders"]) > 0),
                "not-trumpable": (lambda t, _: not t["Trumpable"]),
                "unseen": (lambda t, m: not m["Seen"]),
                "unsnatched": (lambda t, m: not m["Snatched"]),
            }
            for (name, func) in simple_filter_dict.items():
                if name.lower() in subprofile.split(" "):
                    matches = [t for t in matches if func(t, self)]
                    LOGGER.debug(
                        "%i matches after filtering by parameter '%s'",
                        len(matches),
                        name,
                    )
            # lambdas that take a torrent, a function for comparison, and a value-as-a-string
            comparative_filter_dict = {
                "seeders": (lambda t, f, v: f(int(t["Seeders"]), int(v))),
                "size": (lambda t, f, v: f(int(t["Size"]), human_to_bytes(v))),
            }
            comparisons = {
                ">": operator.gt,
                ">=": operator.ge,
                "=": operator.eq,
                "==": operator.eq,
                "!=": operator.ne,
                "<>": operator.ne,
                "<": operator.lt,
                "<=": operator.le,
            }
            for (name, func) in comparative_filter_dict.items():
                match = re.search(r"\b%s([<>=!]+)(.+?)\b" % name, subprofile)
                if match is not None:
                    comp_func = comparisons[match.group(1)]
                    value = match.group(2)
                    matches = [t for t in matches if func(t, comp_func, value)]
                    LOGGER.debug(
                        "%i matches after filtering by parameter '%s'",
                        len(matches),
                        name,
                    )
            sort_dict = {
                "most recent": (
                    True,
                    (lambda t: datetime.strptime(t["UploadTime"], "%Y-%m-%d %H:%M:%S")),
                ),
                "smallest": (False, (lambda t: human_to_bytes(t["Size"]))),
                "most seeders": (True, (lambda t: int(t["Seeders"]))),
                "largest": (True, (lambda t: human_to_bytes(t["Size"]))),
            }
            if len(matches) == 1:
                return matches[0]
            elif len(matches) > 1:
                for name, (rev, sort) in sort_dict.items():
                    if name in subprofile:
                        current_sort = name
                if current_sort is None:
                    current_sort = "most recent"
                LOGGER.debug("Sorting by parameter %s", current_sort)
                (rev, sort) = sort_dict[current_sort]
                return sorted(matches, key=sort, reverse=rev)[0]
        LOGGER.info("Could not find best match for movie %s", self.ID)
        return None
