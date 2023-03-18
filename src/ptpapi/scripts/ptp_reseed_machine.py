#!/usr/bin/env python
"""The reseed machine runs a scan against prowlarr to find potential
reseeds."""
import argparse
import logging

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
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel)
    logger = logging.getLogger("reseed-machine")

    ptp = ptpapi.login()

    if args.id:
        movies = args.id
    else:
        filters = {}
        if args.search:
            for arg in args.search.split(","):
                filters[arg.split("=")[0]] = arg.split("=")[1]
        movies = [t["Link"] for t in ptp.need_for_seed(filters)][: args.limit]

    for i in movies:
        ptp_movie = None
        if "://passthepopcorn.me" in i:
            parsed_url = parse_qs(urlparse(i).query)
            ptp_movie = ptpapi.Movie(ID=parsed_url["id"][0])
            torrent_id = int(parsed_url.get("torrentid", ["0"])[0])

        if ptp_movie is None:
            logger.error("Could not figure out ID '{0}'".format(i))
        else:
            try:
                ptp_movie["ImdbId"]
            except KeyError:
                logger.warning("ImdbId not found from '{0}', skipping".format(i))
                continue
            if ptp_movie["ImdbId"]:
                find_match(ptp_movie, torrent_id)


# Stolen from https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#Python
def levenshtein(s1: str, s2: str):
    """Measure the edit distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)  # pylint: disable=arguments-out-of-order

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
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


def match_results(ptp_result: dict, other_result: dict, title_distance=1) -> dict:
    logger = logging.getLogger("reseed-machine.match")
    percent_diff = 1
    if (
        "imdbid" in other_result
        and other_result["imdbid"]
        and ptp_result["imdbId"] != other_result["imdbId"]
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
        if other_result["indexer"] == "PassThePopcorn":
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


def bytes_to_human(b: int):
    for count in ["B", "KiB", "MiB", "GiB"]:
        if b < 1024.0:
            return "%3.1f %s" % (b, count)
        b /= 1024.0
    return "%3.1f TiB" % b


def find_match(ptp_movie, torrent_id=0):
    logger = logging.getLogger("reseed-machine.find")
    session = requests.Session()
    session.headers.update({"X-Api-Key": config.get("Prowlarr", "api_key")})
    resp = session.get(
        urljoin(config.get("Prowlarr", "url"), "api/v1/search"),
        params={
            "query": "{ImdbId:" + ptp_movie["ImdbId"] + "}",
            "categories": "2000",
            "type": "movie",
        },
    ).json()

    # Some indexers return completely irrelevant results when the
    # title isn't present.
    ignore_title_indexers = [
        i
        for i in config.get("ReseedMachine", "ignoreTitleResults", fallback="").split(
            ","
        )
        if i
    ]
    for result in resp:
        if result["indexer"] == "PassThePopcorn" and result["seeders"] == 0:
            if torrent_id and f"torrentid={torrent_id}" not in result.get(
                "infoUrl", ""
            ):
                continue
            logger.info(
                "Working torrent %s (size %s (%s), sortTitle '%s')",
                result["title"],
                result["size"],
                bytes_to_human(int(result["size"])),
                result["sortTitle"],
            )
            download = {}
            for other_result in resp:
                download = match_results(result, other_result)
                if download:
                    break
            # If no match found, search again by release title
            if not download:
                release_title_resp = session.get(
                    urljoin(config.get("Prowlarr", "url"), "api/v1/search"),
                    params={
                        "query": result["title"],
                        "type": "search",
                        "limit": 100,
                    },
                ).json()
                for release_result in release_title_resp:
                    if release_result["indexer"] not in ignore_title_indexers:
                        download = match_results(result, release_result)
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


if __name__ == "__main__":
    main()
