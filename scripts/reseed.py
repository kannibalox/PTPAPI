#!/usr/bin/env python
import sys
import re
import os
import os.path
import xmlrpclib
import argparse
import ConfigParser
import logging
import readline
import htmlentitydefs
from time import sleep
from urlparse import urlparse, parse_qs

from pyrobase import bencode
from pyrocore import config
from pyrocore.util import load_config, metafile

import ptpapi

logger = logging.getLogger(__name__)

def match_by_torrent(torrent, filepath, dry_run=False, action='soft'):
    logger.debug("Attempting to match against torrent {0} ({1})".format(torrent.ID, torrent.ReleaseName.encode('UTF-8')))
    
    path1 = os.path.abspath(filepath)
    path1_files = {}
    if os.path.isdir(path1):
        for root, directories, filenames in os.walk(path1):
            for filename in filenames:
                f = os.path.join(root, filename).replace(os.path.dirname(path1) + os.sep, '')
                path1_files[f] = os.path.getsize(os.path.join(root, filename))
    elif os.path.isfile(path1):
        path1_files[path1.replace(os.path.dirname(path1) + os.sep, '')] = os.path.getsize(path1)

    path2_files = dict((os.path.join(torrent.ReleaseName, f), int(s)) for f, s in torrent.Filelist.items())

    matched_files = {}
    logger.debug("Looking for exact matches")
    for filename, size in path1_files.items():
        if filename in path2_files.keys() and path2_files[filename] == size:
            matched_files[filename] = filename
            del path1_files[filename]
            del path2_files[filename]
    logger.debug("{0} of {1} files matched".format(len(matched_files), len(path1_files) + len(matched_files)))

    # If the match is 1:1, no need to go through with the rest of the rigmarole
    if len(path1_files) == 0:
        logger.debug("Found exact file match, returning early")
        return path1

    logger.debug("Looking for matches with same size and name but different root folder")
    for filename1, size1 in path1_files.items():
        no_root1 = os.sep.join(os.path.normpath(filename1).split(os.sep)[1:])
        for filename2, size2 in path2_files.items():
            no_root2 = os.sep.join(os.path.normpath(filename2).split(os.sep)[1:])
            if no_root1 == no_root2 and size1 == size2:
                matched_files[filename1] = filename2
                del path1_files[filename1]
                del path2_files[filename2]
                break
    logger.debug("{0} of {1} files matched".format(len(matched_files), len(path1_files) + len(matched_files)))

    logger.debug("Looking for matches with same base name and size")
    for filename1, size1 in path1_files.items():
        for filename2, size2 in path2_files.items():
            if os.path.basename(filename1) == os.path.basename(filename2) and size1 == size2:
                if os.path.basename(filename1) not in [os.path.basename(f) for f in path2_files.keys()]:
                    matched_files[filename1] = filename2
                    del path1_files[filename1]
                    del path2_files[filename2]
                    break
    logger.debug("{0} of {1} files matched".format(len(matched_files), len(path1_files) + len(matched_files)))

    logger.debug("Looking for matches by size only")
    for filename1, size1 in path1_files.items():
        for filename2, size2 in path2_files.items():
            if size1 == size2 and path2_files.values().count(size2) == 1:
                matched_files[filename1] = filename2
                del path1_files[filename1]
                del path2_files[filename2]
                break            
    logger.debug("{0} of {1} files matched".format(len(matched_files), len(path1_files) + len(matched_files)))

    if len(path2_files) > 0:
        logger.debug("Not all files could be matched, returning...")
        return None

    # Start creating the matched files

    if dry_run: 
        logger.debug("Skipping file creation")
    else:
        for origin_file, matched_file in matched_files.items():
            origin_file = os.path.join(os.path.dirname(path1), origin_file)
            file_to_create = os.path.join(os.path.dirname(path1), matched_file)
            path_to_create = os.path.dirname(file_to_create)
            if not os.path.exists(path_to_create):
                try:
                    logger.debug("Creating directory '{0}'".format(path_to_create))
                    os.makedirs(path_to_create)
                except OSError as e:
                    if e.errno != 17:
                        raise
            if os.path.lexists(file_to_create):
                logger.debug("File '{0}' already exists, skipping creation".format(file_to_create))
                continue
            logger.debug("Creating file '{0}' from '{1}' via action '{2}'".format(file_to_create, origin_file, action))
            print os.path.relpath(origin_file, os.path.dirname(file_to_create))
            if action == 'soft':
                os.symlink(os.path.relpath(origin_file, os.path.dirname(file_to_create)), file_to_create)
            elif action == 'hard':
                os.link(origin_file, file_to_create)
    return os.path.join(os.path.dirname(path1), torrent.ReleaseName)

def match_by_movie(movie, filename):
    logger.debug("Attempting to match against movie {0} ({1})".format(movie.ID, movie.Title))

    movie.load_html_data()
    for t in movie.Torrents:
        match = match_by_torrent(t, os.path.abspath(filename))
        if match:
            return (t.ID, match)
    return None

def find_by_file(ptp, filepath):
    filepath = os.path.abspath(filepath)
    tID = None
    if not os.path.exists(filepath):
        logger.error("File/directory {0} does not exist".format(filepath))
        return
    logger.debug("Searching movies by file list")
    for m in ptp.search({'filelist':os.path.basename(filepath)}):
        match = match_by_movie(m, filepath)
        if match:
            return match
    match = guess_by_name(ptp, filepath)
    if match:
        return match
    return None

def guess_by_name(ptp, filepath, name=None):
    filepath = os.path.abspath(filepath)
    try:
        import guessit
    except ImportError:
        logger.debug("Error importing 'guessit' module, skipping name guess")
    logger.debug("Guessing name from filepath with guessit")
    if not name:
        name = os.path.basename(filepath)
    guess = guessit.guess_movie_info(name)
    if guess['title']:
        movies = ptp.search({'searchstr': guess['title']})
        if len(movies) == 0:
            movies = ptp.search({'searchstr': guess['title'], 'inallakas':'1'})
        for m in movies:
            match = match_by_movie(m, filepath)
            if match:
                return match


def load_torrent(proxy, ID, path):
    torrent = ptpapi.Torrent(ID=ID)
    torrent_data = torrent.download()
    data = bencode.bdecode(torrent_data)
    thash = metafile.info_hash(data)
    try:
        logger.debug("Testing for hash {0}".format(proxy.d.hash(thash, fail_silently=True)))
        logger.error("Hash {0} already exists in rtorrent as {1}, cannot load.".format(thash, proxy.d.name(thash)))
        return
    except xmlrpclib.Fault:
        pass
    proxy.load_raw(xmlrpclib.Binary(torrent_data))
    # Wait until the torrent is loaded and available
    while True:
        sleep(1)
        try:
            proxy.d.hash(thash, fail_silently=True)
            break
        except xmlrpclib.Fault:
            pass
    logger.info("Torrent loaded at {0}".format(path))
    proxy.d.directory_base.set(thash, path)
    proxy.d.check_hash(thash)

def main():
    parser = argparse.ArgumentParser(description='Attempt to find and reseed torrents on PTP')
    parser.add_argument('-u', '--url', help='Permalink to the torrent page')
    parser.add_argument('-p', '--path', help='Base directory of the file')
    parser.add_argument('file', help='Path directly to file/directory', nargs='?')
    parser.add_argument('-n', '--dry-run', help="Don't actually create any files or load torrents", action="store_true")
    parser.add_argument('-a', '--action', help="Method to use when creating files", choices=['hard', 'soft'])
    parser.add_argument('--loop', help="Run in loop mode to avoid rapid session creation", action="store_true")
    parser.add_argument('--batch', help='Take a list of file names to process (stdin by default)', type=argparse.FileType('r'), nargs='?', const=sys.stdin, default=None)
    parser.add_argument('--debug', help='Print lots of debugging statements', action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument('-v', '--verbose', help='Be verbose', action="store_const", dest="loglevel", const=logging.INFO)
    parser.add_argument('-q', '--quiet', help='Don\'t show any messages', action="store_const", dest="loglevel", const=logging.CRITICAL)
    args = parser.parse_args()
    
    logging.basicConfig(level=args.loglevel)

    # Load pyroscope
    load_config.ConfigLoader().load()
    proxy = config.engine.open()    

    # Futile attempt to impose our loglevel upon pyroscope
    logging.basicConfig(level=args.loglevel)

    # Load PTP API
    ptp = ptpapi.login()

    if args.batch:
        logger.debug("Reading in file names from {0}".format(args.batch))
        for line in args.batch:
            match = find_by_file(ptp, line.rstrip('\n').decode('UTF-8'))
            if match:
                if not args.dry_run:
                    load_torrent(proxy, *match)
            else:
                logger.error("Could not find match for file {0}".format(line.rstrip('\n').decode('UTF-8')))
        return

    if args.loop:
        print "Entering file read loop. Enter 'q', 'quit' or 'exit' to exit the loop."
        while True:
            filepath = raw_input('file>>> ').decode('UTF-8')
            if filepath in ['q', 'quit', 'exit']:
                break
            match = find_by_file(ptp, filepath)
            if match:
                if not args.dry_run:
                    load_torrent(proxy, *match)
            else:
                logger.error("Could not find match for file {0}".format(line.rstrip('\n').decode('UTF-8')))
        return

    # These are the two variables absolutely required to load a torrent
    path = None
    tID = None

    if args.file:
        arg_file = args.file.decode('UTF-8')

    if args.url:
        parsed_url = parse_qs(urlparse(args.url).query)#['torrentid'][0]
        if arts.path:
            path = arg_file
        elif 'torrentid' in parsed_url:
            path = match_by_torrent(ptpapi.Torrent(ID=parsed_url['torrentid'][0]), arg_file)
            if path:
                tID = parsed_url['torrentid'][0]
        elif 'id' in parsed_url:
            match = match_by_movie(ptpapi.Movie(ID=parsed_url['id'][0]), arg_file)
            if match:
                (tID, path) = match
    elif arg_file:
        match = find_by_file(ptp, arg_file)
        if match:
            (tID, path) = match

    # Make sure we have the minimum information required
    if not tID or not path:
        logger.error("Could not find an associated torrent, cannot reseed")
        ptp.logout()
        return

    logger.info("Found match, now loading torrent {0} to path {1}".format(tID, path.encode('UTF-8')))
    if args.dry_run:
        logger.debug("Stopping before loading")
        ptp.logout()
        return
    load_torrent(proxy, tID, path)

    ptp.logout()

    logger.debug("Exiting...")

if __name__ == '__main__':
    main()
