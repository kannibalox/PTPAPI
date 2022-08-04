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
                find_match(
                    ptp_movie,
                    [],
                    max_ptp_seeds=args.min_ptp_seeds,
                    remote_seeds=args.required_remote_seeds,
                )


def find_match(ptp_movie, sites, max_ptp_seeds=0, remote_seeds=0):
    logger = logging.getLogger(__name__)
    print("tt" + ptp_movie["ImdbId"])
    resp = requests.get(
        config.get("Prowlarr", "url") + "api/v1/search",
        params={
            "query": "{ImdbId:" + ptp_movie["ImdbId"] + "}",
            "indexerIds": "-2",
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
            for other_result in resp:
                size_diff = abs(((other_result["size"] / result["size"]) - 1) * 100)
                if (
                    other_result["indexer"] != "PassThePopcorn"
                    and other_result["seeders"] > 0
                    and 0 < size_diff < percent_diff
                ):
                    print(
                        "match: other {} ptp {} == {}% size diff".format(
                            other_result["size"], result["size"], size_diff
                        )
                    )
                    r = requests.get(other_result["downloadUrl"])
                    r.raise_for_status()
                    name = (
                        re.search(r'filename="(.*)"', r.headers["Content-Disposition"])
                        .group(1)
                        .replace("/", "_")
                    )
                    dest = os.path.join(config.get("Main", "downloadDirectory"), name)
                    with open(dest, "wb") as fh:
                        fh.write(r.content)
                elif other_result["indexer"] != "PassThePopcorn":
                    logger.debug(
                        "{}: {} seeders, {} size diff".format(
                            other_result["indexer"], other_result["seeders"], size_diff
                        )
                    )


if __name__ == "__main__":
    main()
