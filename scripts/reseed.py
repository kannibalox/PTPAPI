#!/bin/env python
import sys
import re
import os
import os.path
import xmlrpclib
import argparse
import ConfigParser
import logging

from pyrobase import bencode
from pyrocore import config
from pyrocore.util import load_config, metafile

import ptpapi

parser = argparse.ArgumentParser(description='Attempt to find and reseed torrents on PTP')
parser.add_argument('-u', '--url', help='Permalink to the torrent page')
parser.add_argument('-p', '--path', help='Base directory of the file')
parser.add_argument('-f', '--file', help='Path directly to file/directory')
parser.add_argument('-c', '--cred', help='Credential file', default="creds.ini")
parser.add_argument('-n', '--dry-run', help="Don't actually load any torrents", action="store_true")
parser.add_argument('--debug', help='Print lots of debugging statements', action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
parser.add_argument('-v', '--verbose', help='Be verbose', action="store_const", dest="loglevel", const=logging.INFO)

args = parser.parse_args()

logging.basicConfig(level=args.loglevel)
logger = logging.getLogger(__name__)
path = args.path
tID = None

# Load APIs
ptp = ptpapi.login()

load_config.ConfigLoader().load()
proxy = config.engine.open()

if args.url:
    tID = re.search(r'(\d+)$', args.url).group(1)
    if not path and args.file:
        path = os.path.dirname(os.path.abspath(args.file))
else:
    if args.file:
        basename = os.path.basename(os.path.abspath(args.file))
        dirname = os.path.dirname(os.path.abspath(args.file))
        for m in ptp.search({'filelist':basename}):
            logger.debug("Found movie %s: %s" % (m.ID, m.Title))
            for t in m.Torrents:
                logger.debug("Found torrent %s under movie %s" % (t.ID, m.ID))
                # Exact match or match without file extension
                if t.ReleaseName == basename or t.ReleaseName == os.path.splitext(basename)[0]:
                    logger.info("Found strong match by release name at", t.ID)
                    tID = t.ID
                    path = dirname
                    break
                elif t.ReleaseName in basename:
                    logger.debug("Found weak match by name at", t.ID)
            if not tID:
                logger.debug("Movie found but no match by release name, going through filelists")
                m.load_html_data()
                for t in m.Torrents:
                    # Only single files under a directory are matched currently
                    # e.g. Movie.Name.Year.mkv -> Move Name (Year)/Movie.Name.Year.mkv
                    if len(t.Filelist) == 1 and t.Filelist.keys()[0] == basename:
                        logger.info("Found strong match by filename at torrent %s, creating new folder struction" % t.ID)
                        tID  = t.ID
                        path = os.path.join(dirname, t.ReleaseName)
                        if not os.path.exists(path):
                            os.mkdir(path)
                        os.link(os.path.abspath(args.file),
                                os.path.join(dirname,
                                             t.ReleaseName,
                                             basename))
                        break
    else:
        raise Exception("No file specified")

# Make sure we have the minimum information required
if not tID or not path:
    logger.error("Torrent ID or path missing, cannot reseed")
    ptp.logout()
    exit()
if args.dry_run:
    ptp.logout()
    exit()

torrent = ptpapi.Torrent(ID=tID)
name = torrent.download_to_file()
ptp.logout()
torrent = metafile.Metafile(name)
data = bencode.bread(name)
thash = metafile.info_hash(data)
try:
    proxy.d.hash(thash, fail_silently=True)
    logger.error("Hash already exists in rtorrent, cannot load.")
    exit()
except xmlrpclib.Fault:
    pass
proxy.load(os.path.abspath(name))
# Wait until the torrent is loaded and available
while True:
    try:
        proxy.d.hash(thash, fail_silently=True)
        break
    except xmlrpclib.Fault:
        pass
logger.info("Torrent loaded")
proxy.d.ignore_commands.set(thash, 1)
proxy.d.directory_base.set(thash, path)
proxy.d.check_hash(thash)

# Cleanup
os.remove(name)
logger.debug("Exiting...")
