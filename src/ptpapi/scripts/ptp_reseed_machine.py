#!/usr/bin/env python
import argparse
import logging
import os
import re

from urllib.parse import parse_qs, urlparse

import requests

import ptpapi

from ptpapi.config import config


class DownloadFoundException(Exception):
    pass


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
        help="The number of seeds required on the remote site",
        default=1,
        type=int,
    )
    parser.add_argument(
        "-m",
        "--min-ptp-seeds",
        help="Set the minimum number of seeds before a reseed will happen",
        default=0,
        type=int,
    )
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel)
    logger = logging.getLogger("reseed-machine")

    logger.info("Logging into PTP")
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

        if ptp_movie is None:
            logger.error("Could not figure out ID '{0}'".format(i))
        else:
            try:
                ptp_movie["ImdbId"]
            except KeyError:
                logger.warning("ImdbId not found from '{0}', skipping".format(i))
                continue
            if ptp_movie["ImdbId"]:
                find_match(ptp_movie)


def match_results(ptp_result, other_result):
    logger = logging.getLogger(__name__)
    download = {}
    percent_diff = 1
    if other_result["protocol"] == "torrent":
        size_diff = round(
            abs(((other_result["size"] / ptp_result["size"]) - 1) * 100), 2
        )
        if (
            other_result["indexer"] != "PassThePopcorn"
            and other_result["seeders"] > 0
            and 0 <= size_diff < percent_diff
        ):
            logger.info(
                "match: %s (%s) and ptp (%s), with %d%% size diff",
                other_result["indexer"],
                other_result["size"],
                ptp_result["size"],
                size_diff,
            )
            download = {
                "guid": other_result["guid"],
                "indexerId": other_result["indexerId"],
                "sortTitle": other_result["sortTitle"],
            }
    elif other_result["protocol"] == "usenet":
        # Usenet sizes vary wildly based on PAR2 levels,
        # etc, so size comparisons aren't as useful
        size_diff = 0
        if other_result["title"] == ptp_result["title"]:
            download = {
                "guid": other_result["guid"],
                "indexerId": other_result["indexerId"],
                "sortTitle": other_result["sortTitle"],
            }
    return download


def find_match(ptp_movie):
    logger = logging.getLogger(__name__)
    resp = requests.get(
        config.get("Prowlarr", "url") + "api/v1/search",
        params={
            "query": "{ImdbId:" + ptp_movie["ImdbId"] + "}",
            "categories": "2000",
            "type": "movie",
        },
        headers={"X-Api-Key": config.get("Prowlarr", "api_key")},
    ).json()
    percent_diff = 1

    # print(resp)
    for result in resp:
        if result["indexer"] == "PassThePopcorn" and result["seeders"] == 0:
            logger.debug("Working {}".format(result["title"]))
            download = {}
            for other_result in resp:
                download = match_results(result, other_result)
                if download:
                    break
            # If no match found, search again by release title
            if not download:
                release_title_resp = requests.get(
                    config.get("Prowlarr", "url") + "api/v1/search",
                    params={
                        "query": result["title"],
                        "type": "search",
                        "limit": 100,
                    },
                    headers={"X-Api-Key": config.get("Prowlarr", "api_key")},
                ).json()
                for release_result in release_title_resp:
                    download = match_results(result, release_result)
                    if download:
                        break

            if download:
                r = requests.post(
                    config.get("Prowlarr", "url") + "api/v1/search/bulk",
                    json=[
                        {
                            "guid": other_result["guid"],
                            "indexerId": other_result["indexerId"],
                            "sortTitle": other_result["sortTitle"],
                        }
                    ],
                    headers={"X-Api-Key": config.get("Prowlarr", "api_key")},
                )
                r.raise_for_status()
            elif other_result["indexer"] != "PassThePopcorn":
                logger.debug(
                    "{}: {} seeders".format(
                        other_result["indexer"],
                        other_result["seeders"],
                    )
                )


if __name__ == "__main__":
    main()
