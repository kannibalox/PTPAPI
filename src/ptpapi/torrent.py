"""Represent a single torrent object"""
import logging
import os
import re
import html

from urllib.parse import parse_qs, urlparse

import humanize

from bs4 import BeautifulSoup as bs4

from ptpapi import movie
from ptpapi.config import config
from ptpapi.error import PTPAPIException
from ptpapi.session import session


LOGGER = logging.getLogger(__name__)


class Torrent:
    """Represent a single torrent"""

    def __init__(self, ID=None, data=None):
        self.key_finder = {
            "movie_json": [
                "Checked",
                "Codec",
                "Container",
                "GoldenPopcorn",
                "GroupId",
                "InfoHash",
                "Leechers",
                "Quality",
                "ReleaseGroup",
                "ReleaseName",
                "RemasterTitle",
                "Resolution",
                "Scene",
                "Seeders",
                "Size",
                "Snatched",
                "Source",
                "UploadTime",
            ],
            "torrent_json": ["Description", "Nfo"],
            "movie_html": ["Filelist"],
            "inferred": ["Link", "Id", "HumanSize"],
            "torrent_description": ["BBCodeDescription"],
            "parent": [
                "Movie"  # Would be 'inferred' if it didn't have a chance to trigger a request
            ],
        }

        if data:
            self.data = data
            if "Id" in data:
                self.ID = data["Id"]  # pylint: disable=invalid-name
            elif "TorrentId" in data:
                self.ID = data["TorrentId"]
            else:
                raise PTPAPIException("Could not find torrent ID in data")
        elif ID:
            self.ID = ID
            self.data = {"Id": ID}
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
            for k, value in self.key_finder.items():
                if name in value:
                    getattr(self, "load_%s_data" % k)()
        return self.data[name]

    def __setitem__(self, key, value):
        self.data[key] = value

    def items(self):
        """Passthru for underlying dict"""
        return self.data.items()

    def keys(self):
        """Passthru for underlying dict"""
        return self.data.keys()

    def load_torrent_description_data(self):
        self.data["BBCodeDescription"] = html.unescape(session.base_get(
            "torrents.php", params={"id": self.ID, "action": "get_description"}
        ).text)

    def load_movie_html_data(self):
        """Get data from the parent movie's JSON data"""
        if "GroupId" not in self.data or not self.data["GroupId"]:
            movie_url = session.base_get(
                "torrents.php", params={"torrentid": self.ID}
            ).url
            self.data["GroupId"] = parse_qs(urlparse(movie_url).query)["id"][0]
        soup = bs4(
            session.base_get(
                "torrents.php", params={"id": self.data["GroupId"], "json": 0}
            ).content,
            "html.parser",
        )
        filediv = soup.find("div", id="files_%s" % self.ID)
        self.data["Filelist"] = {}
        for elem in filediv.find("tbody").find_all("tr"):
            bytesize = (
                elem("td")[1]("span")[0]["title"].replace(",", "").replace(" bytes", "")
            )
            self.data["Filelist"][elem("td")[0].string] = bytesize
        # Check if trumpable
        if soup.find("trumpable_%s" % self.ID):
            self.data["Trumpable"] = [
                s.get_text() for s in soup.find("trumpable_%s" % self.ID).find("span")
            ]
        else:
            self.data["Trumpable"] = []

    def load_movie_json_data(self):
        """Load data from the movie page"""
        LOGGER.debug("Loading Torrent data from movie JSON page.")
        if "GroupId" not in self.data or not self.data["GroupId"]:
            movie_url = session.base_get(
                "torrents.php", params={"torrentid": self.ID}
            ).url
            self.data["GroupId"] = re.search(r"\?id=(\d+)", movie_url).group(1)
        movie_data = session.base_get(
            "torrents.php",
            params={"torrentid": self.ID, "id": self.data["GroupId"], "json": "1"},
        ).json()
        for tor in movie_data["Torrents"]:
            if int(tor["Id"]) == int(self.ID):
                # Fill in any optional fields
                for key in ["RemasterTitle"]:
                    if key not in self.data:
                        self.data[key] = ""
                self.data.update(tor)
                break

    def load_inferred_data(self):
        self.data["Id"] = self.ID
        self.data["Link"] = "https://passthepopcorn.me/torrents.php?torrentid=" + str(
            self.ID
        )
        self.data["HumanSize"] = humanize.naturalsize(
            int(self.data["Size"]), binary=True
        )

    def load_parent_data(self):
        self.data["Movie"] = movie.Movie(ID=self["GroupId"])

    def load_torrent_json_data(self):
        """Load torrent data from a JSON call"""
        LOGGER.debug("Loading Torrent data from torrent JSON page.")
        if "GroupId" not in self.data or not self.data["GroupId"]:
            movie_url = session.base_get(
                "torrents.php", params={"torrentid": self.ID}
            ).url
            self.data["GroupId"] = re.search(r"\?id=(\d+)", movie_url).group(1)
        self.data.update(
            session.base_get(
                "torrents.php",
                params={
                    "action": "description",
                    "id": self.data["GroupId"],
                    "torrentid": self.ID,
                },
            ).json()
        )
        if "Nfo" in self.data and self.data["Nfo"]:
            self.data["Nfo"] = html.unescape(self.data["Nfo"])

    def download(self, params=None):
        """Download the torrent contents"""
        if params is None:
            params = {}
        req_params = params.copy()
        req_params.update({"action": "download", "id": self.ID})
        req = session.base_get("torrents.php", params=req_params)
        return req.content

    def download_to_dir(self, dest=None, params=None):
        """Convenience method to download directly to a directory"""
        if params is None:
            params = {}
        req_params = params.copy()
        req_params.update({"action": "download", "id": self.ID})
        req = session.base_get("torrents.php", params=req_params)
        if not dest:
            dest = config.get("Main", "downloadDirectory")
        name = re.search(r'filename="(.*)"', req.headers["Content-Disposition"]).group(
            1
        )
        dest = os.path.join(dest, name)
        with open(dest, "wb") as fileh:
            fileh.write(req.content)
        return dest
