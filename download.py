#!/bin/env python
# Download a torrent from a url
import ptpapi
import argparse
import os
import re
import sys

parser = argparse.ArgumentParser(description='Download a torrent directly from ptp')
parser.add_argument('-c', '--cred', help='Credential file', default="creds.ini")
parser.add_argument('url', help='The permalink to download the file from')
parser.add_argument('destination', help='The location to save the file', nargs='?', default=os.getcwd())
args = parser.parse_args()

ptp = ptpapi.API()
ptp.login(args.cred)
match = re.search(r'torrentid=(\d+)', args.url)
if not match:
    print "Invalid url - no torrent id found"
    sys.exit(2)
d = ptpapi.Torrent(ID=match.group(1)).download()
name = re.search(r'filename="(.*)"', d.headers['Content-Disposition']).group(1)
ptp.logout()
with open(os.path.join(args.destination, name), 'wb') as fh:
    fh.write(d.content)
