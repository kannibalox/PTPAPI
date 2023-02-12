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

YAML = ruamel.yaml.YAML()
YAML.top_level_colon_align = True
YAML.width = float("inf")
YAML.allow_unicode = True

RE_COMMENT = re.compile(
    r"https://passthepopcorn.me/torrents.php\?id=(\d+)&torrentid=(\d+)"
)
RE_URL = re.compile(
    r"((http|https)\:\/\/)[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
)
RE_DELETED_BY = re.compile(r"was deleted by .* for")


def write_origin(t, args):
    logger = logging.getLogger(__name__)
    mfile_path = Path(t)
    mfile = metafile.Metafile.from_file(mfile_path)
    if "comment" not in mfile or not RE_COMMENT.match(mfile["comment"]):
        logger.info("Skipping file %s, does not contain PTP URL in comment", t)
        return
    logger.info("Working file %s", t)
    match = RE_COMMENT.match(mfile["comment"])
    movie = ptpapi.Movie(match.group(1))
    torrent = ptpapi.Torrent(data={"Id": match.group(2), "GroupId": match.group(1)})
    if args.output_directory is not None:
        output_dir = args.output_directory
    else:
        output_dir = Path(mfile_path.stem)
    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = Path(output_dir, mfile_path.with_suffix(".yaml").name)
    nfo_path = Path(output_dir, mfile_path.with_suffix(".nfo").name)
    logger.info("Writing origin YAML file %s", yaml_path)
    stream = yaml_path.open("w")
    stream.write("---")
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
    YAML.dump(data, stream)
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
    YAML.dump({"Log": log_data}, stream)
    stream.close()
    # NFO
    if "Nfo" in torrent.data and torrent["Nfo"]:
        logger.info("Writing NFO file %s", nfo_path)
        nfo_path.write_text(torrent["Nfo"])
    # Download anything that looks like a URL
    if not args.no_images:
        for m in re.finditer(RE_URL, desc):
            url_parts = urlparse(m.group(0))
            path = Path(output_dir, Path(url_parts.path).name)
            # Skip IMDb title URLS
            if "imdb.com/title/" not in m.group(0) and not path.exists():
                logger.info("Downloading description image %s to %s", m.group(0), path)
                resp = requests.get(m.group(0))
                if resp.headers["Content-Type"].startswith("image"):
                    with path.open("wb") as fh:
                        fh.write(resp.content)
        # Cover
        url_parts = urlparse(movie["Cover"])
        path = Path(output_dir, Path(url_parts.path).name)
        if not path.exists():
            logger.info("Downloading cover %s to %s", movie["Cover"], path)
            resp = requests.get(m.group(0))
            if resp.headers["Content-Type"].startswith("image"):
                with path.open("wb") as fh:
                    fh.write(resp.content)


def main():
    parser = argparse.ArgumentParser(
        usage="Download metadata from PTP for archival purposes"
    )
    parser.add_argument(
        "torrent", nargs="+", help="Torrent file to use for scraping information"
    )
    parser.add_argument(
        "--debug",
        help="Print lots of debugging statements",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Be verbose",
        action="store_const",
        dest="loglevel",
        const=logging.INFO,
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="Hide most messages",
        action="store_const",
        dest="loglevel",
        const=logging.CRITICAL,
    )
    parser.add_argument(
        "-r", "--recursive", help="Recursively walk directory", action="store_true"
    )
    parser.add_argument(
        "-d",
        "--output-directory",
        help="Directory to write files to (defaults to torrent name without extension)",
        metavar="DIR",
    )
    parser.add_argument(
        "--no-images", help="Skip downloading images", action="store_true"
    )
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    logger = logging.getLogger(__name__)
    ptpapi.login()
    stream = sys.stdout
    file_iter = args.torrent
    for p in args.torrent:
        p_path = Path(p)
        if p_path.is_dir():
            if args.recursive:
                for t in p_path.rglob("*.torrent"):
                    write_origin(t, args)
            else:
                logger.warning(
                    "Skipping directory %s, use --recursive to descend into directories",
                    p,
                )
        if p_path.is_file():
            write_origin(p, args)


if __name__ == "__main__":
    main()
