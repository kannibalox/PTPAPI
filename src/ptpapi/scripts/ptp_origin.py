#!/usr/bin/env python
import logging

import argparse
import re
import sys
import textwrap
from urllib.parse import urlparse
from pathlib import Path

import requests
import ruamel.yaml
import ptpapi
from pyrosimple.util import metafile
from bs4 import BeautifulSoup as bs4

RE_COMMENT = re.compile(
    r"https://passthepopcorn.me/torrents.php\?id=(\d+)&torrentid=(\d+)"
)
RE_URL = re.compile(
    r"((http|https)\:\/\/)[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
)
RE_DELETED_BY = re.compile(r"was deleted by .* for")


def main():
    parser = argparse.ArgumentParser(
        usage="Download metadata from PTP for archival purposes"
    )
    parser.add_argument("torrent", nargs="+")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    ptpapi.login()
    stream = sys.stdout
    yaml = ruamel.yaml.YAML()
    yaml.top_level_colon_align = True
    yaml.width = float("inf")
    yaml.allow_unicode = True
    for t in args.torrent:
        mfile = metafile.Metafile.from_file(Path(t))
        if "comment" not in mfile or not RE_COMMENT.match(mfile["comment"]):
            continue
        match = RE_COMMENT.match(mfile["comment"])
        movie = ptpapi.Movie(match.group(1))
        torrent = ptpapi.Torrent(data={"Id": match.group(2), "GroupId": match.group(1)})
        result = "---\n"
        # Basic data
        data = {
            "Title": movie["Name"],
            "Year": int(movie["Year"]),
            "Directors": movie["Directors"],
            "ReleaseName": torrent["ReleaseName"],
            "RemasterTitle": torrent["RemasterTitle"],
            "IMDb": f'https://imdb.com/title/tt{movie["ImdbId"]}',
            "Cover": movie["Cover"],
            "Permalink": mfile["comment"],
            "InfoHash": torrent["InfoHash"],
            "Codec": torrent["Codec"],
            "Container": torrent["Container"],
            "UploadTime": torrent["UploadTime"],
            "Checked": torrent["Checked"],
            "GoldenPopcorn": torrent["GoldenPopcorn"],
            "Scene": torrent["Scene"],
            "ReleaseGroup": torrent["ReleaseGroup"],
            "Resolution": torrent["Resolution"],
            "Size": int(torrent["Size"]),
            "Source": torrent["Source"],
            "Tags": movie["Tags"],
        }
        max_key_len = max(len(k) for k in data)
        yaml.dump(data, stream)
        # Nicely format multi-line descriptions
        desc = torrent["BBCodeDescription"]
        stream.write("Description: |\n")
        stream.write(
            textwrap.indent(
                desc,
                "  ",
            )
        )
        stream.write("\n")
        # Scrubbed deletion log
        soup = bs4(
            ptpapi.session.session.base_get(
                "torrents.php",
                params={
                    "action": "history_log",
                    "groupid": movie.ID,
                    "search": "",
                    "only_deletions": 1,
                },
            ).content,
            features="html.parser",
        )
        log_body = soup.find("tbody")
        log_data = []
        for row in log_body.find_all("tr"):
            time = row.find_all("span")[0]["title"]
            message = RE_DELETED_BY.sub("was deleted for", row.find_all("span")[1].text)
            if message != row.find_all("span")[1].text:
                log_data.append({"Time": time, "Message": message.strip()})
        yaml.dump({"Log": log_data}, stream)
        # Download any URL that looks like a URL
        for m in re.finditer(RE_URL, desc):
            url_parts = urlparse(m.group(0))
            path = Path(Path(url_parts.path).name)
            if "imdb.com/title/" not in m.group(0) and not path.exists():
                resp = requests.get(m.group(0))
                if resp.headers["Content-Type"].startswith("image"):
                    with path.open("wb") as fh:
                        fh.write(resp.content)
        continue


if __name__ == "__main__":
    main()
