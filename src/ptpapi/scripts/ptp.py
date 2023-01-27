#!/usr/bin/env python
import argparse
import logging
import os.path

from time import sleep
from urllib.parse import parse_qs, urlparse

import tempita

from bs4 import BeautifulSoup as bs4

import ptpapi


def ellipsize(string, length):
    if len(string) > length:
        return string[: length - 3] + "..."
    return string


def do_inbox(api, args):
    page = args.page
    user = api.current_user()
    if args.mark_all_read:
        print("Clearing out {0} messages".format(user.get_num_messages()))
        while user.new_messages > 0:
            for msg in api.current_user().inbox(page=page):
                if msg["Unread"] is False:
                    continue
                user.inbox_conv(msg["ID"])
            page += 1
    elif args.conversation:
        conv = user.inbox_conv(args.conversation)
        print(conv["Subject"])
        for msg in conv["Message"]:
            print("{0} - {1}\n".format(msg["User"], msg["Time"]))
            print(msg["Text"])
            print("----------------------------")
    elif args.mark_read:
        for conv in args.mark_read:
            user.inbox_conv(conv)
    else:
        msgs = list(user.inbox(page=page))
        print("ID" + " " * 8 + "Subject" + " " * 25 + "Sender" + " " * 9)
        print("-" * 55)
        for msg in msgs:
            if args.unread and msg["Unread"] is False:
                continue
            if args.user is not None and msg["Sender"] != args.user:
                continue
            print(
                "{0: <10}{1: <32}{2: <15}".format(
                    msg["ID"],
                    ellipsize(msg["Subject"].decode("utf-8"), 31),
                    ellipsize(msg["Sender"], 15),
                )
            )


def parse_terms(termlist):
    """Takes an array of terms, and sorts them out into 4 categories:
    * torrent URLs
    * movie URLs
    * targets (where to perform the search e.g. collages or bookmarks)
    * all other search parameters
    """
    torrents = []
    movies = []
    terms = {}
    target = "torrents"

    for arg in termlist:
        url = urlparse(arg)
        url_args = parse_qs(url.query)
        if url.path == "/collages.php":
            target = "collage"
            terms = url_args
        elif url.path == "/artist.php":
            target = "artist"
            terms = url_args
        elif url.path == "/torrents.php":
            if "torrentid" in url_args:
                torrents.append(ptpapi.Torrent(url_args["torrentid"][0]))
            elif "id" in url_args:
                if "action" in url_args and url_args["action"][0] == "download":
                    torrents.append(ptpapi.Torrent(url_args["id"][0]))
                else:
                    movies.append(ptpapi.Movie(url_args["id"][0]))
            else:
                terms = url_args
        else:
            term = arg.partition("=")
            if not term[2]:
                if term[0] == "bookmarks":
                    target = "bookmarks"
                else:
                    terms["searchstr"] = term[0]
            else:
                # Provide aliases for commonly used terms
                term_map = {
                    "taglist": ["genre", "genres", "tags"],
                    "searchstr": ["name", "title"],
                }
                for key, value in term_map.items():
                    if term[0] in value:
                        term = (key, term[1], term[2])
                terms[term[0]] = term[2]
    return (target, movies, torrents, terms)


def get_pages(target, terms):
    if target == "torrents":
        return ptpapi.util.find_page_range(
            ptpapi.session.session.base_get("torrents.php", params=terms).content
        )
    return None


def do_search(api, args):
    (target, movies, torrents, terms) = parse_terms(args.search_terms)
    if args.all:
        args.pages = get_pages(target, terms)
        logger = logging.getLogger(__name__)
        logger.debug("Auto-detected maximum page as %s")
    if "page" not in terms:
        terms["page"] = "1"
    else:
        page = terms["page"][0]
        terms["page"] = page
    for _ in range(args.pages):
        search_page(api, args, target, movies, torrents, terms.copy())
        terms["page"] = str(int(terms["page"]) + 1)


def search_page(api, args, target, movies, torrents, terms):
    logger = logging.getLogger(__name__)
    if args.movie_format == "":
        movie_template = None  # Just to make linting happy
    elif args.movie_format is not None:
        movie_template = tempita.Template(args.movie_format)
    else:
        movie_template = tempita.Template(
            "{{Title}} ({{Year}}) - {{if Directors}}{{','.join([d['Name'].strip() for d in Directors])}} -{{endif}} "
            "[{{'/'.join(Tags)}}] - [PTP {{GroupId}}{{if ImdbId}}, IMDB tt{{ImdbId}}{{endif}}]"
        )
    if args.torrent_format == "":
        torrent_template = None
    elif args.torrent_format is not None:
        torrent_template = tempita.Template(args.torrent_format)
    else:
        torrent_template = tempita.Template(
            "{{if GoldenPopcorn}}\u2606{{else}}-{{endif}} {{Codec}}/{{Container}}/{{Source}}/{{Resolution}}"
            " - {{ReleaseName}} - {{Snatched}}/{{Seeders}}/{{Leechers}}"
        )

    # If we haven't found any URL-looking things
    if not movies and not torrents:
        logger.debug('Attempting to search target "%s" with terms %s', target, terms)
        if target == "torrents":
            movies = api.search(terms)
            # Check to see if we should scrape the cover view data to save calls
            wanted_fields = set(
                [l[2].split("|")[0] for l in movie_template._parsed if l[0] == "expr"]
            )
            if len(wanted_fields & set(api.search_coverview_fields)):
                for movie in api.search_coverview(terms):
                    for ret_movie in movies:
                        if movie["GroupId"] == ret_movie["GroupId"]:
                            ret_movie.update(movie)
        elif target == "bookmarks":
            movies = api.current_user().bookmarks(search_terms=terms)
        elif target == "collage":
            movies = api.collage(terms["id"], terms)
        elif target == "artist":
            movies = api.artist(terms["id"], terms)
        movies = movies[: args.limit]

    if args.download:
        for movie in movies[: args.limit]:
            if movie_template:
                print(movie_template.substitute(movie))
            match = movie.best_match(args.filter)
            if match:
                if torrent_template:
                    print(torrent_template.substitute(match))
                if not args.dry_run:
                    match.download_to_dir(args.output_directory)
                else:
                    logger.info("Dry-run, not downloading %s", match)
            else:
                logger.info(
                    "No match found for for movie %s (%s)",
                    movie["Title"],
                    movie["Year"],
                )
        for torrent in torrents:
            if args.download and not args.dry_run:
                if torrent_template:
                    print(torrent_template.substitute(torrent))
                torrent.download_to_dir(args.output_directory)
            elif args.dry_run:
                logger.info("Dry-run, not downloading %s", torrent)
    else:
        for movie in movies[: args.limit]:
            if movie_template:
                print(movie_template.substitute(movie))
            for torrent in movie["Torrents"]:
                if torrent_template:
                    print(torrent_template.substitute(torrent))
        for torrent in torrents:
            if torrent_template:
                print(torrent_template.substitute(torrent))


def do_raw(_, args):
    """Given a URL, download the raw HTML to the current directory"""
    for url_str in args.url:
        url = urlparse(url_str)
        data = ptpapi.session.session.base_get("?".join([url.path, url.query])).content
        if args.output:
            if args.output == "-":
                print(data.decode(), end="")
                return
            else:
                file_out = args.output
        else:
            file_out = os.path.basename(url.path)
        with open(file_out, "wb") as fileh:
            fileh.write(data)


def do_log(api, args):
    interval = 30.0
    lastmsg = None
    while True:
        printmsg = False
        msgs = api.log()
        # We actually want it 'reversed' by default, with the newest at the bottom
        if not args.reverse:
            msgs.reverse()
        for time, msg in msgs:
            if lastmsg is None or printmsg:
                print(time, "-", msg)
                lastmsg = msg
            if lastmsg == msg:
                printmsg = True
        if args.follow:
            sleep(interval)
        else:
            break


def do_fields(api, args):
    print("Movie:")
    m = ptpapi.Movie(ID=1)
    for values in m.key_finder.values():
        for val in values:
            print(f"- {val}")
    print("Torrent:")
    t = ptpapi.Torrent(ID=1)
    for values in t.key_finder.values():
        for val in values:
            print(f"- {val}")


def do_search_fields(api, args):
    soup = bs4(
        ptpapi.session.session.base_get(
            "torrents.php", params={"action": "advanced", "json": "0"}
        ).content,
        "html.parser",
    )
    for e in soup.find(id="filter_torrents_form")("input"):
        if (
            e["type"] in ["submit", "button"]
            or e["name"].startswith("filter_cat")
            or e["name"].startswith("tags_type")
            or e["name"].startswith("country_type")
            or e["name"] == "action"
        ):
            continue
        name = e["name"]
        if "placeholder" in e.attrs.keys():
            name += " - " + e["placeholder"]
        if "title" in e.attrs.keys():
            name += " - " + e["title"]
        print(name)


def do_userstats(api, args):
    if args.user_id:
        user = ptpapi.User(args.user_id)
    else:
        user = api.current_user()
    if args.hummingbird:
        # e.g. '[ Example ] :: [ Power User ] :: [ Uploaded: 10.241 TiB | Downloaded: 1.448 TiB | Points: 79,76g2,506 | Ratio: 2.58 ] :: [ https://passthepopcorn.me/user.php?id=XXXXX ]'
        stats = user.stats()
        stats["Id"] = user.ID
        print(
            "[ {{Username}} ] :: [ {Class} ] :: [ Uploaded: {Uploaded} | Downloaded: {Downloaded} | Points: {Points} | Ratio: {Ratio} ] :: [ https://passthepopcorn.me/user.php?id={Id} ]".format(
                **stats
            )
        )
    else:
        for stat, value in user.stats().items():
            print(stat + ": " + value)


def do_archive(api, args):
    r = ptpapi.session.session.base_get(
        "archive.php",
        params={
            "action": "fetch",
            "MaxStalled": 0,
            "ContainerName": ptpapi.config.config.get("PTP", "archiveContainerName"),
            "ContainerSize": ptpapi.config.config.get("PTP", "archiveContainerSize"),
        },
    )
    r.raise_for_status()
    data = r.json()
    ptpapi.Torrent(ID=data["TorrentID"]).download_to_dir(
        params={"ArchiveID": data["ArchiveID"]}
    )
    if args.download_incomplete:
        for _id, i_data in data["IncompleteTransactions"].items():
            if i_data["InfoHash"] is not None:
                ptpapi.Torrent(ID=i_data["TorrentID"]).download_to_dir(
                    params={"ArchiveID": data["ArchiveID"]}
                )


def add_verbosity_args(parser):
    """Helper function to improve DRY"""
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


def main():
    logger = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(
        description="Extensible command line utility for PTP"
    )
    parser.set_defaults(func=None)
    add_verbosity_args(parser)
    subparsers = parser.add_subparsers()

    # Search & download
    search_parent = argparse.ArgumentParser()
    add_verbosity_args(search_parent)
    search_parent.add_argument(
        "search_terms",
        help="""A list of terms in [field]=[text] format.
        If the '=' is omitted, the field is assumed to be 'name'.""",
        nargs="+",
        metavar="term",
    )
    search_parent.add_argument(
        "-n",
        "--dry-run",
        help="Don't actually download any torrents",
        action="store_true",
    )
    search_parent.add_argument(
        "-l", "--limit", help="Limit search results to N movies", default=100, type=int
    )
    search_parent.add_argument(
        "-f",
        "--filter",
        help="Define a filter to download movies with",
        default=ptpapi.config.config.get("Main", "filter"),
    )
    search_parent.add_argument(
        "-m", "--movie-format", help="Set the output for movies", default=None
    )
    search_parent.add_argument(
        "-t", "--torrent-format", help="Set the output for torrents", default=None
    )
    search_parent.add_argument(
        "-o",
        "--output-directory",
        help="Location for any downloaded files",
        default=None,
    )
    search_parent.add_argument(
        "-p", "--pages", help="The number of pages to download", default=1, type=int
    )
    search_parent.add_argument(
        "-a", "--all", help="Return all search results", action="store_true"
    )

    # Search
    search_parser = subparsers.add_parser(
        "search",
        help="Search for or download movies",
        add_help=False,
        parents=[search_parent],
    )
    search_parser.add_argument(
        "-d", "--download", help="Download any movies found", action="store_true"
    )
    search_parser.set_defaults(func=do_search)

    # Download
    download_parser = subparsers.add_parser(
        "download",
        help="An alias for `search -d`",
        add_help=False,
        parents=[search_parent],
    )
    download_parser.add_argument(
        "-d",
        "--download",
        help="Download any movies found",
        action="store_true",
        default=True,
    )
    download_parser.set_defaults(func=do_search)

    # Archive
    archive_parser = subparsers.add_parser(
        "archive", help="Commands related to the archive project."
    )
    archive_parser.add_argument(
        "--download-incomplete",
        help="Also download any incomplete transactions",
        action="store_true",
    )
    archive_parser.set_defaults(func=do_archive)

    # Inbox
    inbox_parser = subparsers.add_parser("inbox", help="Reads messages in your inbox")
    add_verbosity_args(inbox_parser)
    inbox_parser.add_argument(
        "-u", "--unread", help="Only show unread messages", action="store_true"
    )
    inbox_parser.add_argument(
        "-m",
        "--mark-read",
        help="Mark messages as read",
        type=lambda s: [int(n) for n in s.split(",")],
    )
    inbox_parser.add_argument(
        "--mark-all-read",
        help="Scan and mark all messages as read. "
        "WARNING: If new messages arrive while this is running, the script can get caught in a loop until it reaches the end of the inbox's pages",
        action="store_true",
    )
    inbox_parser.add_argument("--user", help="Filter messages by the sender")
    inbox_parser.add_argument(
        "-c",
        "--conversation",
        help="Get the messages of a specific conversation",
        type=int,
    )
    inbox_parser.add_argument(
        "-p", "--page", help="Start at a certain page", type=int, default=1
    )
    inbox_parser.set_defaults(func=do_inbox)

    raw_parser = subparsers.add_parser("raw", help="Fetch the raw HTML of pages")
    add_verbosity_args(raw_parser)
    raw_parser.add_argument("url", help="A list of urls to download", nargs="+")
    raw_parser.add_argument(
        "-o",
        "--output",
        help="Set output file (or - for stdout)",
    )
    raw_parser.set_defaults(func=do_raw)

    # User stats
    userstats_parser = subparsers.add_parser(
        "userstats", help="Gather users' stats from profile pages"
    )
    add_verbosity_args(userstats_parser)
    userstats_parser.add_argument(
        "-i", "--user-id", help="The user to look at", nargs="?", default=None
    )
    userstats_parser.add_argument(
        "--hummingbird", help="Imitate Hummingbird's format", action="store_true"
    )
    userstats_parser.set_defaults(func=do_userstats)

    # Fields
    field_parser = subparsers.add_parser(
        "fields", help="List the fields available for each PTPAPI resource"
    )
    add_verbosity_args(field_parser)
    field_parser.set_defaults(func=do_fields)

    search_field_parser = subparsers.add_parser(
        "search-fields", help="List the fields available when searching"
    )
    add_verbosity_args(search_field_parser)
    search_field_parser.set_defaults(func=do_search_fields)

    log_parser = subparsers.add_parser("log", help="Show the log of recent events")
    add_verbosity_args(log_parser)
    log_parser.add_argument(
        "-r", "--reverse", help="Sort in reverse", action="store_true"
    )
    log_parser.add_argument(
        "-f", "--follow", help="Print new entries as they appear", action="store_true"
    )
    log_parser.set_defaults(func=do_log)

    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel)

    api = ptpapi.login()

    if args.func is None:
        parser.print_help()
        return
    args.func(api, args)
    logger.debug(
        "Total session tokens consumed: %s", ptpapi.session.session.consumed_tokens
    )
    logger.debug("Exiting...")


if __name__ == "__main__":
    main()
