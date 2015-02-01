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
from time import sleep
from urlparse import urlparse, parse_qs

from pyrobase import bencode
from pyrocore import config
from pyrocore.util import load_config, metafile

import ptpapi

logger = logging.getLogger(__name__)

def match_by_torrent(torrent, filepath, dry_run=False, action='soft'):
    logger.debug("Attempting to match against torrent {0} ({1})".format(torrent.ID, torrent.ReleaseName))
    
    path1 = os.path.abspath(filepath)
    path1_files = {}
    if os.path.isdir(path1):
        for root, directories, filenames in os.walk(path1):
            for filename in filenames:
                f = os.path.join(root, filename).replace(os.path.dirname(path1), '')
                path1_files[f] = os.path.getsize(f)
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
            if os.path.exists(file_to_create):
                logger.debug("File '{0}' already exists, skipping creation".format(file_to_create))
                continue
            logger.debug("Creating file '{0}' from '{1}' via action '{2}'".format(file_to_create, origin_file, action))
            print os.path.relpath(origin_file, file_to_create)
            if action == 'soft':
                os.symlink(os.path.relpath(origin_file, file_to_create), file_to_create)
            elif action == 'hard':
                os.link(origin_file, file_to_create)

def match_by_movie(movie, filename):
    logger.debug("Attempting to match against movie {0} ({1})".format(movie.ID, movie.Title))
    filename = os.path.abspath(filename)
    basename = os.path.basename(os.path.abspath(filename))
    dirname = os.path.dirname(os.path.abspath(filename))
    tID = None
    for t in movie.Torrents:
        # Exact match or match without file extension
        if t.ReleaseName == basename or t.ReleaseName == os.path.splitext(basename)[0]:
            logger.info("Found strong match by release name at {0}".format(t.ID))
            tID = t.ID
            if os.path.isdir(filename):
                path = filename
            else:
                path = dirname
            return (tID, path)
        elif t.ReleaseName in basename:
            logger.debug("Found weak match by name against torrent {0} ({1})".format(t.ID, t.ReleaseName))
    if not tID:
        logger.debug("No match by release name, attempting to match to torrent files")
        movie.load_html_data()
        for t in movie.Torrents:
            match = match_by_torrent(t, filename)
            if match:
                return match

def find_by_file(ptp, filepath):
    filename = os.path.abspath(filepath)
    basename = os.path.basename(os.path.abspath(filename))
    dirname = os.path.dirname(os.path.abspath(filename))
    tID = None
    if not os.path.exists(filename):
        logger.error("File/directory {0} does not exist".format(filename))
        return
    for m in ptp.search({'filelist':basename}):
        logger.debug("Found movie {0}: {1}".format(m.ID, m.Title))
        match = match_by_movie(m, filename)
        if match:
            return match
    return None

def guess_by_name(ptp, filepath, name=None):
    filename = os.path.abspath(filepath)
    basename = os.path.basename(os.path.abspath(filename))
    dirname = os.path.dirname(os.path.abspath(filename))
    try:
        import guessit
    except ImportError:
        logger.debug("Error importing 'guessit' module, skipping name guess")
    logger.debug("Guessing name from filename with guessit")
    filename = os.path.abspath(filepath)
    if not name:
        name = os.path.basename(os.path.abspath(filename))
    guess = guessit.guess_movie_info(name)
    if guess['title']:
        for m in ptp.search({'searchstr': guess['title']}):
            match_by_movie(m, filename)

def load_torrent(proxy, ID, path):
    torrent = ptpapi.Torrent(ID=ID)
    name = torrent.download_to_file()
    data = bencode.bread(name)
    thash = metafile.info_hash(data)
    try:
        logger.debug("Testing for hash {0}".format(proxy.d.hash(thash, fail_silently=True)))
        logger.error("Hash {0} already exists in rtorrent as {1}, cannot load.".format(thash, proxy.d.name(thash)))
        os.remove(name)
        return
    except xmlrpclib.Fault:
        pass
    proxy.load(os.path.abspath(name))
    # Wait until the torrent is loaded and available
    while True:
        sleep(1)
        try:
            proxy.d.hash(thash, fail_silently=True)
            break
        except xmlrpclib.Fault:
            pass
    logger.info("Torrent loaded at {0}".format(path))
    proxy.d.ignore_commands.set(thash, 1)
    proxy.d.directory_base.set(thash, path)
    proxy.d.check_hash(thash)

    # Cleanup
    os.remove(name)

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

    guess_by_name(ptp, args.file)
    exit(1)

    if args.batch:
        logger.debug("Reading in file names from {0}".format(args.batch))
        for line in args.batch:
            match = find_by_file(ptp, line.rstrip('\n').decode('UTF-8'))
            if match and not args.dry_run:
                load_torrent(proxy, *match)
            else:
                logger.error("Could not find match for file {0}".format(line.rstrip('\n').decode('UTF-8')))
        return

    if args.loop:
        logger.debug("Begin file read loop")
        while True:
            filepath = raw_input('file>>> ').decode('UTF-8')
            if filepath in ['q', 'quit', 'exit']:
                break
            match = find_by_file(ptp, filepath)
            if match and not args.dry_run:
                load_torrent(proxy, *match)
            else:
                logger.error("Could not find match for file {0}".format(line.rstrip('\n').decode('UTF-8')))
        return

    path = unicode(args.path)
    if args.file:
        arg_file = args.file.decode('UTF-8')
    tID = None

    if args.url:
        tID = parse_qs(urlparse(args.url).query)['torrentid'][0]
        if not path and arg_file:
            path = unicode(os.path.dirname(os.path.abspath(arg_file)))
    else:
        if arg_file:
            match = find_by_file(ptp, arg_file)
            if match:
                (tID, path) = match
        else:
            raise Exception("No file specified")

    # Make sure we have the minimum information required
    if not tID or not path:
        logger.error("Could not find an associated torrent, cannot reseed")
        ptp.logout()
        return
    logger.info("Found match, now loading torrent {0} to path {1}".format(tID, path))
    if args.dry_run:
        logger.debug("Stopping before loading")
        ptp.logout()
        return
    load_torrent(proxy, tID, path)

    ptp.logout()

    logger.debug("Exiting...")

if __name__ == '__main__':
    main()
