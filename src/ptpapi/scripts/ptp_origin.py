#!/usr/bin/env python
import logging
from urllib.parse import urlparse

import argparse
import re
import sys
import textwrap
from pathlib import Path

import requests
import ruamel.yaml
import ptpapi
from pyrosimple.util import metafile

yaml = ruamel.yaml.YAML()
RE_COMMENT = re.compile(
    r"https://passthepopcorn.me/torrents.php\?id=(\d+)&torrentid=(\d+)"
)
RE_URL = re.compile(
    r"((http|https)\:\/\/)[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
)


def main():
    parser = argparse.ArgumentParser(
        usage="Download metadata from PTP for archival purposes"
    )
    parser.add_argument("torrent", nargs="+")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG)
    ptpapi.login()
    stream = sys.stdout
    for t in args.torrent:
        mfile = metafile.Metafile.from_file(Path(t))
        if "comment" not in mfile or not RE_COMMENT.match(mfile["comment"]):
            continue
        match = RE_COMMENT.match(mfile["comment"])
        movie = ptpapi.Movie(match.group(1))
        torrent = ptpapi.Torrent(data={"Id": match.group(2), "GroupId": match.group(1)})
        result = "---\n"
        data = {
            "Title": movie["Name"],
            "Year": int(movie["Year"]),
            "Directors": movie["Directors"],
            "Tags": movie["Tags"],
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
        }
        max_key_len = max(len(k) for k in data)
        yaml.top_level_colon_align = True
        yaml.width = float("inf")
        yaml.allow_unicode = True
        yaml.dump(data, stream)
        desc = torrent["BBCodeDescription"]
        stream.write("Description: |\n")
        stream.write(
            textwrap.indent(
                torrent["BBCodeDescription"],
                "  ",
            )
        )
        for m in re.finditer(RE_URL, desc):
            url_parts = urlparse(m.group(0))
            path = Path(Path(url_parts.path).name)
            if "imdb.com/title/" not in m.group(0) and not path.exists():
                resp = requests.get(m.group(0))
                if resp.headers["Content-Type"].startswith("image"):
                    with path.open("wb") as fh:
                        fh.write(resp.content)


if __name__ == "__main__":
    main()
