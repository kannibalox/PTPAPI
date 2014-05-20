#!/bin/env python
import sys
import re
import os
import os.path
import xmlrpclib
import argparse

from pyrobase import bencode
from pyrocore import config
from pyrocore.util import load_config, metafile
from ptpapi import PTPAPI

parser = argparse.ArgumentParser(description='Attempt to find and reseed torrents on PTP')
parser.add_argument('-u', '--url', help='Permalink to the torrent page')
parser.add_argument('-p', '--path', help='Base directory of the file')
parser.add_argument('-f', '--file', help='Path directly to file/directory')
parser.add_argument('-n', '--dry-run', help='Don\'t actually log in or load any torrents', action="store_true")

# Load APIs
ptp = PTPAPI()
ptp.login()
load_config.ConfigLoader().load()
proxy = config.engine.open()

# Process flags
args = parser.parse_args()
path = args.path
tID = None
if args.url:
    tID = re.search(r'(\d+)$', args.url).group(1)
else:
    if args.file:
        basename = os.path.basename(os.path.abspath(args.file))
        for m in ptp.search({'filelist':basename})['Movies']:
            print "Movie %s: %s - %s/torrents.php?id=%s" % (m['GroupId'], m['Title'], ptp.baseURL, m['GroupId'])
            for t in m['Torrents']:
                # Exact match or match with out file extension
                if t['ReleaseName'] == basename or t['ReleaseName'] == os.path.splitext(basename)[0]:
                    print "Found strong match by name at", t['Id']
                    tID = t['Id']
                    path = os.path.dirname(os.path.abspath(args.file))
                    break
                elif t['ReleaseName'] in basename:
                    print "Found weak match by name at", t['Id']
            if not tID:
                print "Movie found but no match"
    else:
        raise Exception

if args.dry_run:
    exit()
# Make sure we have the minimum information required
if not tID or not path:
    print "Torrent ID or path missing, cannot reseed"
    exit()

(name, data) = ptp.downloadTorrent(tID)
with open(name, 'wb') as fh:
    fh.write(data.read())
torrent = metafile.Metafile(name)
data = bencode.bread(name)
thash = metafile.info_hash(data)
try:
    proxy.d.hash(thash)
    print "Hash already exists in rtorrent, cannot load."
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
proxy.d.ignore_commands.set(thash, 1)
proxy.d.directory_base.set(thash, path)
proxy.d.check_hash(thash)

# Cleanup
ptp.logout()
os.remove(name)
print "Exiting..."
