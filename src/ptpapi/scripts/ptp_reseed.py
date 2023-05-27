#!/usr/bin/env python
"""Reseed a torrent from PTP, given a path"""
import argparse
import logging
import os
import os.path
import sys

from pathlib import Path
from time import sleep, time
from typing import Optional, Union
from urllib.parse import parse_qs, urlparse
from xmlrpc import client as xmlrpc_client

import bencode
import bencodepy
import libtc
import pyrosimple

from pyrosimple.util import metafile, rpc

import ptpapi


class Match:
    """A tiny class to make matching easier

    Could be expanded to introduce a confidence indicator

    ID is an integer-as-a-string, and path is filepath"""

    # pylint: disable=too-few-public-methods
    def __init__(
        self,
        ID: Optional[str] = None,
        path: Optional[os.PathLike] = None,
        matched_files: Optional[dict[str, str]] = None,
        failure_reason: str = "No match",
    ):
        """A defined match"""
        self.ID = ID
        self.path = path
        if matched_files is None:
            matched_files = {}
        self.matched_files = matched_files
        self.failure_reason = failure_reason

    def __nonzero__(self):
        if self.ID is not None and self.path is not None:
            return True
        return False

    def __bool__(self):
        return self.__nonzero__()

    def __str__(self):
        return "<Match {0}:{1}>".format(self.ID, self.path)


def match_by_torrent(torrent, filepath: str) -> Match:
    """Attempt matching against a torrent ID"""
    logger = logging.getLogger(__name__)
    logger.info(
        "Attempting to match against torrent {0} ({1})".format(
            torrent.ID, torrent["ReleaseName"]
        )
    )

    if isinstance(filepath, bytes):
        filepath = filepath.decode("utf-8")
    path1 = os.path.abspath(filepath)
    path1_files = {}
    if os.path.isdir(path1):
        for root, _, filenames in os.walk(path1, followlinks=True):
            for filename in filenames:
                realpath = os.path.join(root, filename).replace(
                    os.path.dirname(path1) + os.sep, ""
                )
                path1_files[realpath] = os.path.getsize(os.path.join(root, filename))
    elif os.path.isfile(path1):
        path1_files[os.path.basename(path1)] = os.path.getsize(path1)

    path2_files = dict((f, int(s)) for f, s in torrent["Filelist"].items())

    if len(path1_files) < len(path2_files):
        logger.debug(
            "Too little files to match torrent ({0} locally, {1} in torrent)".format(
                len(path1_files), len(path2_files)
            )
        )
        return Match(
            None,
            failure_reason="Too little files to match torrent ({0} locally, {1} in torrent)".format(
                len(path1_files), len(path2_files)
            ),
        )

    matched_files = {}
    logger.debug("Looking for exact matches")
    for filename, size in list(path1_files.items()):
        if filename in path2_files.keys() and path2_files[filename] == size:
            matched_files[filename] = filename
            del path1_files[filename]
            del path2_files[filename]
    logger.debug(
        "{0} of {1} files matched".format(
            len(matched_files), len(path2_files) + len(matched_files)
        )
    )

    logger.debug(
        "Looking for matches with same size and name but different root folder"
    )
    for filename1, size1 in list(path1_files.items()):
        no_root1 = os.sep.join(os.path.normpath(filename1).split(os.sep)[1:])
        for filename2, size2 in list(list(path2_files.items())):
            no_root2 = os.sep.join(os.path.normpath(filename2).split(os.sep)[1:])
            if no_root1 == no_root2 and size1 == size2:
                matched_files[filename1] = filename2
                del path1_files[filename1]
                del path2_files[filename2]
                break
    logger.debug(
        "{0} of {1} files matched".format(
            len(matched_files), len(path2_files) + len(matched_files)
        )
    )

    logger.debug("Looking for matches with same base name and size")
    for filename1, size1 in list(path1_files.items()):
        for filename2, size2 in list(path2_files.items()):
            if (
                os.path.basename(filename1) == os.path.basename(filename2)
                and size1 == size2
            ):
                if os.path.basename(filename1) not in [
                    os.path.basename(p) for p in path2_files.keys()
                ]:
                    matched_files[filename1] = filename2
                    del path1_files[filename1]
                    del path2_files[filename2]
                    break
    logger.debug(
        "{0} of {1} files matched".format(
            len(matched_files), len(path2_files) + len(matched_files)
        )
    )

    logger.debug("Looking for matches by size only")
    for filename1, size1 in list(path1_files.items()):
        for filename2, size2 in list(path2_files.items()):
            logger.debug(
                "Comparing size of {0} ({1}) to size of {2} ({3})".format(
                    filename1, size1, filename2, size2
                )
            )
            if size1 == size2:
                logger.debug("Matched {0} to {1}".format(filename1, filename2))
                matched_files[filename1] = filename2
                del path1_files[filename1]
                del path2_files[filename2]
                break
    logger.debug(
        "{0} of {1} files matched".format(
            len(matched_files), len(path2_files) + len(matched_files)
        )
    )

    if len(path2_files) > 0:
        logger.info("Not all files could be matched, returning...")
        return Match(
            None, f"Not all files could be matched ({len(path2_files)} remaining)"
        )
    return Match(torrent.ID, Path(os.path.dirname(path1)), matched_files)


def match_by_movie(movie, filepath) -> Match:
    """Tries to match a torrent against a single movie"""
    logger = logging.getLogger(__name__)
    logger.info(f"Attempting to match against movie {movie.ID} ({movie['Title']})")

    movie.load_html_data()
    for torrent in movie["Torrents"]:
        match = match_by_torrent(torrent, os.path.abspath(filepath))
        if match:
            return match
    return Match(
        None,
        failure_reason="No match found against movie {0} ({1})".format(
            movie.ID, movie["Title"]
        ),
    )


def match_by_guessed_name(ptp, filepath, limit, name=None) -> Match:
    """Use guessit to find the movie by metadata scraped from the filename"""
    logger = logging.getLogger(__name__)
    filepath = os.path.abspath(filepath)
    try:
        import guessit  # pylint: disable=import-error
    except ImportError:
        logger.warning("Error importing 'guessit' module, skipping name guess")
        return Match(None, failure_reason="Error importing 'guessit' module")
    logger.info("Guessing name from filepath with guessit")
    if not name:
        name = os.path.basename(filepath)
    guess = guessit.guessit(name)
    if "title" in guess and guess["title"]:
        search_params = {"searchstr": guess["title"]}
        if "year" in guess:
            search_params["year"] = guess["year"]
        movies = ptp.search(search_params)
        if len(movies) == 0:
            movies = ptp.search({"searchstr": guess["title"], "inallakas": "1"})
        if len(movies) == 0:
            logger.debug("Could not find any movies by search with a guessed name")
            return Match(
                None,
                failure_reason="Could not find any movies by search with a guessed name",
            )
        for movie in movies[:limit]:
            match = match_by_movie(movie, filepath)
            if match:
                return match
    return Match(
        None, failure_reason=f"Could not find match via guessed name {guess['title']}"
    )


def match_against_file(ptp, filepath, movie_limit) -> Match:
    """Use's PTP's file search feature to match a filename to a movie"""
    logger = logging.getLogger(__name__)
    filepath = os.path.abspath(filepath)
    logger.info("Searching movies by file list")
    for movie in ptp.search({"filelist": os.path.basename(filepath)})[:movie_limit]:
        match = match_by_movie(movie, filepath)
        if match:
            return match
    return Match(None, failure_reason="Could not find any match by filename")


def create_matched_files(match, directory=None, action="hard", dry_run=False):
    """Intelligently create any necessary files or directories by different methods"""
    logger = logging.getLogger(__name__)
    if dry_run:
        logger.info("Dry run, no files or directories will be created")
    for origin_file, matched_file in match.matched_files.items():
        origin_file = os.path.join(match.path, origin_file)
        if directory is None:
            directory = match.path
        file_to_create = os.path.join(directory, matched_file)
        path_to_create = os.path.dirname(file_to_create)
        try:
            logger.debug("Creating directory '{0}'".format(path_to_create))
            if not dry_run:
                os.makedirs(path_to_create)
        except OSError as exc:
            # Ignore OSError only if the directory already exists
            if exc.errno != 17:
                raise
        if os.path.lexists(file_to_create):
            logger.debug(
                "File '{0}' already exists, skipping creation".format(file_to_create)
            )
            continue
        logger.info(
            "Creating file '{0}' from '{1}' via action '{2}'".format(
                file_to_create, origin_file, action
            )
        )
        if not dry_run:
            if action == "soft":
                os.symlink(origin_file, file_to_create)
            elif action == "hard":
                os.link(origin_file, file_to_create)
            elif action == "skip":
                continue
    match.path = directory
    return match


def is_torrent_complete(infohash: str, client=None) -> Union[bool, None]:
    """This returns a sort of horrible ternary: None if the torrent
    does not exist, True if it's complete, and false otherwise."""
    if client is None:
        proxy = pyrosimple.connect().open()
        try:
            if proxy.d.complete(infohash):
                return True
            return False
        except rpc.HashNotFound:
            return None
    elif isinstance(client, str) and client.startswith("file://"):
        return None
    else:
        for torrent in client.list():
            if torrent.infohash == infohash:
                if torrent.progress == 100:
                    return True
                return False
        return None


def load_torrent(
    ID, path, client=None, hash_check=False, overwrite_incomplete=False
) -> bool:
    """Send a torrent to rtorrent and kick off the hash recheck"""
    logger = logging.getLogger(__name__)
    torrent = ptpapi.Torrent(ID=ID)
    torrent_data = torrent.download()
    data = metafile.Metafile(bencode.bdecode(torrent_data))
    thash = data.info_hash()
    path = Path(path)
    if hash_check:
        from pyrosimple.util.metafile import PieceFailer

        logger.debug("Starting hash check against %r", str(path))
        pf = PieceFailer(data)
        try:
            check_path = path
            if data.is_multi_file:
                check_path = Path(path, data["info"]["name"])
            data.hash_check(check_path, piece_callback=pf.check_piece)
            data.add_fast_resume(check_path)
        except OSError as exc:
            logger.error("Could not complete hash check: %s", exc)
            return False
    if client is None:
        hash_exists = False
        proxy = pyrosimple.connect().open()
        try:
            logger.debug("Testing for hash {0}".format(proxy.d.hash(thash)))
            if proxy.d.complete(thash):
                logger.error(
                    "Hash {0} is already completed in rtorrent as {1}, cannot load.".format(
                        thash, proxy.d.name(thash)
                    )
                )
                return False
            hash_exists = True
        except rpc.HashNotFound:
            pass
        if hash_exists and not overwrite_incomplete:
            logger.error(
                "Hash {0} already exists in rtorrent as {1}, cannot load.".format(
                    thash, proxy.d.name(thash)
                )
            )
            return False
        proxy.load.raw("", xmlrpc_client.Binary(torrent_data))
        # Wait until the torrent is loaded and available
        while True:
            sleep(1)
            try:
                proxy.d.hash(thash)
                break
            except (xmlrpc_client.Fault, rpc.HashNotFound):
                pass
        logger.info("Torrent loaded at %r", str(path))
        proxy.d.custom.set(thash, "tm_completed", str(int(time())))
        proxy.d.directory.set(thash, str(path))
        if hash_check and not overwrite_incomplete:
            proxy.d.start(thash)
        else:
            proxy.d.check_hash(thash)
        return True
    elif isinstance(client, str) and client.startswith("file://"):
        dest = Path(client[7:], data["info"]["name"] + ".torrent").expanduser()
        logger.info("Saving file to %r", str(dest))
        data.save(dest)
        return True
    else:
        bd = bencodepy.BencodeDecoder()
        return bool(client.add(bd.decode(torrent_data), path))


def define_parser():
    """Define the arguments for the CLI"""
    parser = argparse.ArgumentParser(
        description="Attempt to find and reseed torrents on PTP"
    )
    parser.add_argument("-u", "--url", help="Permalink to the torrent page")
    parser.add_argument(
        "files",
        help="Paths to files/directories to reseed (or leave blank to read stdin)",
        nargs="*",
        type=str,
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        help="Don't actually create any files or load torrents",
        action="store_true",
    )
    parser.add_argument(
        "-a",
        "--action",
        help="Method to use when creating files",
        choices=["hard", "soft", "skip"],
        default=ptpapi.config.config.get("Reseed", "action"),
    )
    parser.add_argument(
        "-d",
        "--create-in-directory",
        help="Directory to create any new files in, if necessary",
        default=None,
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
        "--client",
        help="Experimental: use a custom libtc URL. See https://github.com/JohnDoee/libtc#url-syntax for examples",
        default=ptpapi.config.config.get("Reseed", "client", fallback=None),
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
        help="Don't show any messages",
        action="store_const",
        dest="loglevel",
        const=logging.CRITICAL,
    )
    parser.add_argument(
        "-s", "--summary", help="Show a summary of all actions", action="store_true"
    )
    parser.add_argument(
        "-l",
        "--limit",
        help="Limit the maximum number of movies checked for each file",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--hash-check",
        help="Hash check against any found matches before loading",
        action="store_true",
    )
    parser.add_argument(
        "--overwrite-incomplete",
        help="If the torrent exists as incomplete, change the path of the existing torrent (rtorrent only)",
        action="store_true",
    )
    return parser


def process(cli_args):
    """The entrypoint"""
    parser = define_parser()
    args = parser.parse_args(cli_args)
    logger = logging.getLogger("ptp-reseed")

    logging.basicConfig(level=args.loglevel)

    # Futile attempt to impose our loglevel upon pyroscope
    logging.basicConfig(level=args.loglevel)

    # Load PTP API
    ptp = ptpapi.login()

    loaded = []
    would_load = []
    could_not_load = []
    not_found = []

    if args.files in (["-"], []):
        filelist = sys.stdin
    else:
        filelist = args.files

    loaded_paths = []

    if args.client:
        if args.client[0].startswith("file://"):
            client = args.client[0]
        else:
            client = libtc.parse_libtc_url(args.client)
    else:
        client = None

    for filename in filelist:
        match = Match(None)
        filename = filename.strip("\n")

        logger.info('Starting reseed attempt on file "{0}"'.format(filename))

        if not os.path.exists(filename):
            logger.error("File/directory {0} does not exist".format(filename))
            continue

        if args.url:
            parsed_url = parse_qs(urlparse(args.url).query)
            if "torrentid" in parsed_url:
                match = match_by_torrent(
                    ptpapi.Torrent(ID=parsed_url["torrentid"][0]), filename.encode()
                )
            elif "id" in parsed_url:
                match = match_by_movie(
                    ptpapi.Movie(ID=parsed_url["id"][0]), filename.encode()
                )
        elif filename:
            for match_type in ptpapi.config.config.get("Reseed", "findBy").split(","):
                try:
                    if match_type == "filename":
                        if os.path.abspath(filename) in loaded_paths:
                            logger.info(
                                "Path {0} already in rtorrent, skipping".format(
                                    os.path.abspath(filename)
                                )
                            )
                        else:
                            logger.debug(
                                "Path {0} not in rtorrent".format(
                                    os.path.abspath(filename)
                                )
                            )
                            match = match_against_file(ptp, filename, args.limit)
                    elif match_type == "title":
                        match = match_by_guessed_name(ptp, filename, args.limit)
                    else:
                        logger.error(
                            "Match type {0} not recognized for {1}, skipping".format(
                                match_type, filename
                            )
                        )
                    if match:
                        break
                except Exception:
                    print("Error while attempting to match file '{0}'".format(filename))
                    raise

        # Make sure we have the minimum information required
        if not match:
            not_found.append(filename)
            logger.error(
                "Could not find an associated torrent for '%s', cannot reseed: %s",
                filename,
                match.failure_reason,
            )
            continue

        if args.create_in_directory:
            create_in = args.create_in_directory
        elif ptpapi.config.config.has_option("Reseed", "createInDirectory"):
            create_in = ptpapi.config.config.get("Reseed", "createInDirectory")
        else:
            create_in = None
        create_matched_files(
            match, directory=create_in, action=args.action, dry_run=args.dry_run
        )
        logger.info(
            "Found match, now loading torrent {0} to path {1}".format(
                match.ID, match.path
            )
        )
        match_log_line = (
            f"https://passthepopcorn.me/torrents.php?torrentid={match.ID} -> {filename}"
        )
        if args.dry_run:
            would_load.append(match_log_line)
            logger.debug("Dry-run: Stopping before actual load")
            continue
        if load_torrent(
            match.ID,
            Path(match.path),
            client,
            hash_check=args.hash_check,
            overwrite_incomplete=args.overwrite_incomplete,
        ):
            loaded.append(match_log_line)
        else:
            could_not_load.append(match_log_line)

    if args.summary:
        if loaded:
            print("==> Loaded:")
            print("\n".join(loaded))
        if would_load:
            print("==> Would have loaded:")
            print("\n".join(would_load))
        if could_not_load:
            print("==> Could not load:")
            print("\n".join(could_not_load))
        if not_found:
            print("==> Not found:")
            print("\n".join(not_found))

    exit_code = 0
    if len(not_found) == 1:
        exit_code = 1
    elif len(not_found) > 1:
        exit_code = 2
    elif len(could_not_load) > 0:
        exit_code = 3

    logger.debug(
        "Total session tokens consumed: %s", ptpapi.session.session.consumed_tokens
    )
    logger.debug("Exiting...")
    return exit_code


def main():
    # Load pyroscope
    exit_code = process(sys.argv[1:])
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
