import logging
import os
import re

import bencode
import humanize

from ptpapi.config import config
from ptpapi.session import TokenSession
from ptpapi.sites.base import BaseSiteAPI


class CGAPI(BaseSiteAPI):
    Name = "CG"

    def __init__(self):
        self.baseURL = "https://cinemageddon.net"
        self.session = TokenSession(3, 0.5)
        self.session.headers.update({"User-Agent": "Wget/1.13.4"})
        super().__init__()

    def login(self, username=None, password=None, passkey=None):
        password = password or config.get("CG", "password")
        username = username or config.get("CG", "username")
        response = self.session.post(
            self.baseURL + "/takelogin.php",
            data={"username": username, "password": password},
        )
        response.raise_for_status()
        if response.text.find('action="takelogin.php"') != -1:
            raise CGAPIException("Failed to log in")

    def search(self, search_args):
        search_string = "&".join(
            ["%s=%s" % (key, value) for (key, value) in search_args.items()]
        )
        soup = self._httpRequest("/browse.php?%s" % search_string)
        return self.getTorrentListInfo(soup)

    def find_ptp_movie(self, movie):
        return self.search({"search": "tt{0}".format(movie["ImdbId"])})

    def bytes_to_site_size(self, byte_num):
        humanized = humanize.naturalsize(byte_num, format="%.2f", binary=True)
        if "KiB" in humanized:
            humanized = humanize.naturalsize(byte_num, format="%d", binary=True)
        return humanized

    def getTorrentListInfo(self, soup):
        if not soup.find("table", class_="torrenttable") or not soup.find(
            "table", class_="torrenttable"
        ).find("tbody"):
            return []
        rows = soup.find("table", class_="torrenttable").find("tbody").find_all("tr")
        retArray = []
        for r in rows:
            data = {}
            data["Title"] = r.find("a", href=re.compile(r"details.php\?id=[0-9]+$"))[
                "title"
            ]
            data["BinaryHumanSize"] = (
                r.find(text=re.compile(r"[0-9]+\.[0-9]+ [kA-Z]B"))
                .replace("B", "iB")
                .replace("k", "K")
            )
            data["Seeders"] = re.match(
                r"([0-9]+)", r.find(title=re.compile("[0-9]+ seeders?"))["title"]
            ).group(1)
            data["ID"] = re.match(
                r"details.php\?id=([0-9]+)$",
                r.find("a", href=re.compile(r"details.php\?id=[0-9]+$"))["href"],
            ).group(1)
            retArray.append(data)
        return retArray

    def download_to_file(self, ID, dest=None):
        logger = logging.getLogger(__name__)
        r = self.session.get(self.baseURL + "/download.php", params={"id": ID})
        r.raise_for_status()
        if not dest:
            name = (
                bencode.bdecode(r.content)["info"]["name"].replace("/", "_")
                + ".torrent"
            )
            dest = os.path.join(config.get("Main", "downloadDirectory"), name)
        logger.debug("Downloading ID {} to {}".format(ID, dest.encode("utf-8")))
        with open(dest, "wb") as fh:
            fh.write(r.content)


class CGAPIException(Exception):
    pass


if __name__ == "__main__":
    cg = CGAPI()
    cg.login()
    print(cg.search({"search": "tt0054650"}))
