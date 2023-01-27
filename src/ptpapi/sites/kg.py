import os
import re

import humanize

from ptpapi.config import config
from ptpapi.session import TokenSession
from ptpapi.sites.base import BaseSiteAPI


class KGAPI(BaseSiteAPI):
    Name = "KG"

    def __init__(self):
        self.baseURL = "https://karagarga.in"
        self.session = TokenSession(3, 0.5)
        self.session.headers.update({"User-Agent": "Wget/1.13.4"})
        super().__init__()

    def login(self, username=None, password=None, passkey=None):
        password = password or config.get("KG", "password")
        username = username or config.get("KG", "username")
        response = self.session.post(
            self.baseURL + "/takelogin.php",
            data={"username": username, "password": password},
        ).text
        if response.find('action="takelogin.php"') != -1:
            raise KGAPIException("Failed to log in")

    def search(self, search_args):
        search_string = "&".join(
            ["%s=%s" % (key, value) for (key, value) in search_args.items()]
        )
        soup = self._httpRequest("/browse.php?%s" % search_string)
        return self.getTorrentListInfo(soup)

    def getTorrentListInfo(self, soup):
        if not soup.find("table", id="browse"):
            return []
        retArray = []
        for row in soup.find("table", id="browse").find_all("tr")[1:]:
            if "id" in row.find_all("td")[0].attrs:
                # Only rows used for displaying extra info have IDs; we don't want them
                continue
            cells = row.find_all("td")
            infoDict = {
                "Title": cells[1].b.get_text(),
                "Year": cells[3].get_text(),
                "Seeders": cells[12].get_text(),
                "Leechers": cells[13].get_text(),
                "BinaryHumanSize": re.sub(
                    r"([a-zA-Z])B", r" \1iB", cells[10].get_text()
                ).replace("k", "K"),
            }
            infoDict["ID"] = re.search(r"\d+", cells[1].a["href"]).group(0)
            retArray.append(infoDict)
        return retArray

    def download(self, ID):
        r = self.session.get(self.baseURL + "/down.php/%s/file.torrent" % ID)
        downloadName = re.search(
            r'filename="(.*)"', r.headers["Content-Disposition"]
        ).group(1)
        return (downloadName, r.content)

    def download_to_file(self, ID, dest=None):
        r = self.session.get(self.baseURL + "/down.php/%s/file.torrent" % ID)
        r.raise_for_status()
        if not dest:
            name = (
                re.search(r'filename="(.*)"', r.headers["Content-Disposition"])
                .group(1)
                .replace("/", "_")
            )
            dest = os.path.join(config.get("Main", "downloadDirectory"), name)
        with open(dest, "wb") as fh:
            fh.write(r.content)

    def find_ptp_movie(self, movie):
        return self.search({"search_type": "imdb", "search": movie["ImdbId"]})

    def bytes_to_site_size(self, byte_num):
        humanized = humanize.naturalsize(byte_num, format="%.2f", binary=True)
        if "MiB" in humanized or "KiB" in humanized:
            humanized = humanize.naturalsize(byte_num, format="%d", binary=True)
        return humanized


class KGAPIException(Exception):
    pass


if __name__ == "__main__":
    kg = KGAPI()
    print(kg.search({"search_type": "imdb", "search": "0207295"}))
