#!/usr/bin/env python
"""The reseed machine runs a scan against prowlarr to find potential
reseeds."""
import argparse
import logging
import json
from datetime import datetime
from pathlib import Path

from urllib.parse import parse_qs, urljoin, urlparse

import requests

import ptpapi

from ptpapi.config import config


def main():
    parser = argparse.ArgumentParser(
        description="Attempt to find torrents to reseed on PTP from other sites"
    )
    parser.add_argument("-i", "--id", help="Only full PTP links for now", nargs="*")
    parser.add_argument(
        "--debug",
        help="Print lots of debugging statements",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="Only show error messages",
        action="store_const",
        dest="loglevel",
        const=logging.ERROR,
    )
    parser.add_argument(
        "-l",
        "--limit",
        help="Limit need-for-seed results to N movies",
        default=100,
        type=int,
    )
    parser.add_argument(
        "-s", "--search", help="Allow filtering the need-for-seed results", default=None
    )
    parser.add_argument(
        "--target-tracker",
        help="Specify the tracker to try and reseed to",
        default="PassThePopcorn",
    )
    parser.add_argument(
        "--history-file",
        help="Keep track of previously searched results, and skip duplicate requests",
        default=None,
        type=Path,
    )
    parser.add_argument(
        "-r",
        "--required-remote-seeds",
        help="The number of seeds required on remote torrent",
        default=1,
        type=int,
    )
    parser.add_argument(
        "-m",
        "--min-ptp-seeds",
        help="Set the minimum number of PTP seeds before a reseed attempt will happen",
        default=0,
        type=int,
    )
    parser.add_argument(
        "-t",
        "--query-type",
        help="Set the query type to use (can be specified multiple times)",
        default=[],
        choices=[
            "imdb",
            "title",
            "sortTitle",
            "sortTitleNoQuotes",
            "dotToSpace",
            "spaceToDot",
            "underscoreToDot",
            "underscoreToSpace",
        ],
        action="append",
    )
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel)

    ptp = ptpapi.login()

    if not args.query_type:
        args.query_type = ["imdb", "title"]
    history = []
    if args.history_file and args.history_file.exists():
        for line in args.history_file.read_text().split("\n"):
            if line:
                data = json.loads(line)
                if data["search"]:
                    history.append(data["search"])
    if args.target_tracker == "PassThePopcorn":
        if args.id:
            torrents = []
            for t in args.id:
                if "://passthepopcorn.me" in t:
                    parsed_url = parse_qs(urlparse(t).query)
                    # ptp_movie = ptpapi.Movie(ID=parsed_url["id"][0])
                    torrent_id = int(parsed_url.get("torrentid", ["0"])[0])
                    torrents.append(ptpapi.Torrent(ID=torrent_id))
        else:
            filters = {}
            if args.search:
                for arg in args.search.split(","):
                    filters[arg.split("=")[0]] = arg.split("=")[1]
            torrents = ptp.need_for_seed(filters)[: args.limit]

        for t in torrents:
            if not any(f"torrentid={t.ID}" in h["infoUrl"] for h in history):
                find_match(args, t)


# Stolen from https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#Python
def levenshtein(s1: str, s2: str):
    """Measure the edit distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)  # pylint: disable=arguments-out-of-order

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = (
                previous_row[j + 1] + 1
            )  # j+1 instead of j since previous_row and current_row are one character longer
            deletions = current_row[j] + 1  # than s2
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def sort_title(title: str) -> str:
    sortTitle = ""
    for c in title:
        if c.isalnum():
            sortTitle += c.lower()
        else:
            sortTitle += " "
    splitTitle = sortTitle.split()
    # Clean out articles
    for s in ["a", "the", "of"]:
        try:
            splitTitle.remove(s)
        except ValueError:
            pass
    return " ".join(splitTitle)


def match_results(
    ptp_result: dict, other_result: dict, ignore_tracker: str, title_distance=1
) -> dict:
    logger = logging.getLogger("reseed-machine.match")
    percent_diff = 1
    # How useful is this check? IMDb IDs can change, or may not be present at all
    if (
        "imdbId" in other_result
        and other_result["imdbId"]
        and ptp_result.get("imdbId", "xxx") != other_result["imdbId"]
    ):
        logger.debug(
            "%s IMDb ID mismatch: %s %s %s",
            other_result["protocol"],
            other_result["imdbId"],
            other_result["indexer"],
            other_result["title"],
        )
    if other_result["protocol"] == "torrent":
        size_diff = round(
            abs(((other_result["size"] / ptp_result["size"]) - 1) * 100), 2
        )
        if other_result["indexer"] == ignore_tracker:
            return {}
        if other_result["seeders"] == 0:
            logger.debug(
                "torrent has no seeders: %s %s",
                other_result["indexer"],
                other_result["title"],
            )
            return {}
        if 0 <= size_diff < percent_diff:
            logger.info(
                "torrent size match: %s %s (%s (%s)), with %.2f%% size diff",
                other_result["indexer"],
                other_result["title"],
                other_result["size"],
                bytes_to_human(other_result["size"]),
                size_diff,
            )
            return other_result
        else:
            logger.debug(
                "torrent size mismatch: %s %s (%s (%s)), with %.2f%% size diff",
                other_result["indexer"],
                other_result["title"],
                other_result["size"],
                bytes_to_human(other_result["size"]),
                size_diff,
            )
    elif other_result["protocol"] == "usenet":
        # Usenet sizes vary wildly based on PAR2 levels,
        # etc, so size comparisons aren't very useful
        if levenshtein(other_result["title"], ptp_result["title"]) <= title_distance:
            logger.info(
                "usenet title match: %s (%s)",
                other_result["indexer"],
                other_result["title"],
            )
            return other_result
        else:
            logger.debug(
                "usenet title mismatch: %s",
                other_result["title"],
            )
        # Also check sortTitle if present
        if "sortTitle" in ptp_result and "sortTitle" in other_result:
            if (
                levenshtein(other_result["sortTitle"], ptp_result["sortTitle"])
                <= title_distance
            ):
                logger.info(
                    "usenet sort title match: %s (%s)",
                    other_result["title"],
                    other_result["sortTitle"],
                )
                return other_result
            else:
                logger.debug(
                    "usenet sort title mismatch: %s (%s)",
                    other_result["title"],
                    other_result["sortTitle"],
                )
    return {}


def bytes_to_human(b: float):
    for count in ["B", "KiB", "MiB", "GiB"]:
        if b < 1024.0:
            return "%3.1f %s" % (b, count)
        b /= 1024.0
    return "%3.1f TiB" % b


def find_match(args, torrent):
    logger = logging.getLogger("reseed-machine.find")
    session = requests.Session()
    session.headers.update({"X-Api-Key": config.get("Prowlarr", "api_key")})
    result = {}
    imdb_resp = []  # Might be cached for later usage
    download = {}
    if "imdb" in args.query_type and torrent["Movie"]["ImdbId"]:
        imdb_resp = session.get(
            urljoin(config.get("Prowlarr", "url"), "api/v1/search"),
            params={
                "query": "{ImdbId:" + torrent["Movie"]["ImdbId"] + "}",
                "categories": "2000",
                "type": "movie",
            },
        ).json()
        for r in imdb_resp:
            if r[
                "indexer"
            ] == args.target_tracker and f"torrentid={torrent['Id']}" in r.get(
                "infoUrl", ""
            ):
                result = r
                break
    if not result:
        # Build a result object that resembles what prowlarr would return
        result = {
            "title": torrent["ReleaseName"],
            "size": int(torrent["Size"]),
            "indexer": args.target_tracker,
            "infoUrl": torrent["Link"],
            "sortTitle": sort_title(torrent["ReleaseName"]),
        }
        if torrent["Movie"]["ImdbId"]:
            result.update({"imdbId": torrent["Movie"]["ImdbId"]})
    logger.info(
        "Working torrent %s (size %s (%s), sortTitle '%s')",
        result["title"],
        result["size"],
        bytes_to_human(int(result["size"])),
        result["sortTitle"],
    )

    queries = {
        "title": lambda r: {"query": r["title"]},
        "sortTitle": lambda r: {"query": r["sortTitle"]},
        "sortTitleNoQuotes": lambda r: {
            "query": sort_title(r["title"].replace("'", ""))
        },
        "dotToSpace": lambda r: {"query": r["title"].replace(".", " ")},
        "underscoreToDot": lambda r: {"query": r["title"].replace("_", ".")},
        "underscoreToSpace": lambda r: {"query": r["title"].replace("_", " ")},
        "spaceToDot": lambda r: {"query": r["title"].replace(" ", ".")},
    }

    # Some indexers return completely irrelevant results when the
    # title isn't present.
    ignore_title_indexers = [
        i
        for i in config.get("ReseedMachine", "ignoreTitleResults", fallback="").split(
            ","
        )
        if i
    ]

    # We already have this result from before, and it'll be empty if
    # the imdb query is disabled
    for other_result in imdb_resp:
        download = match_results(result, other_result, args.target_tracker)
        if download:
            break
    if not download:
        for q_type in args.query_type:
            if q_type == "imdb":
                continue
            if download:
                break
            params = queries[q_type](result)
            params.setdefault("type", "search")
            params.setdefault("limit", "100")
            release_title_resp = session.get(
                urljoin(config.get("Prowlarr", "url"), "api/v1/search"),
                params=params,
            ).json()
            for release_result in release_title_resp:
                if release_result["indexer"] not in ignore_title_indexers:
                    download = match_results(
                        result, release_result, args.target_tracker
                    )
                    if download:
                        break
    if download:
        logger.info(
            "Downloading %s (%s) from %s",
            download["title"],
            download["infoUrl"],
            download["indexer"],
        )
        r = session.post(
            urljoin(config.get("Prowlarr", "url"), "api/v1/search"),
            json={
                "guid": download["guid"],
                "indexerId": download["indexerId"],
            },
        )
        r.raise_for_status()
    if args.history_file:
        with args.history_file.open("ta") as fh:
            info_keys = ["title", "infoUrl", "indexer", "imdbId"]
            match_info = {}
            if download:
                match_info = {k: v for k, v in download.items() if k in info_keys}
            search_info = {k: v for k, v in result.items() if k in info_keys}
            fh.write(
                json.dumps(
                    {
                        "checked": datetime.now().isoformat(),
                        "found_match": bool(download),
                        "match": match_info,
                        "search": search_info,
                    }
                )
                + "\n"
            )


if __name__ == "__main__":
    main()
