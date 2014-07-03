#!/bin/env python
# Download a torrent from a url
from ptpapi import PTPAPI
import argparse
import ConfigParser
import os
import re
import sys

parser = argparse.ArgumentParser(description='Download a torrent directly from ptp')
parser.add_argument('-c', '--cred', help='Credential file', default="creds.ini")
parser.add_argument('url', help='The permalink to download the file from')
parser.add_argument('destination', help='The location to save the file', nargs='?', default=os.getcwd())
args = parser.parse_args()

# Load API
configFile = ConfigParser.ConfigParser()
configFile.read(args.cred)
username = configFile.get('PTP', 'username')
password = configFile.get('PTP', 'password')
passkey = configFile.get('PTP', 'passkey')
ptp = PTPAPI()
ptp.login(username, password, passkey)
match = re.search(r'torrentid=(\d+)', args.url)
if not match:
    print "Invalid url - no torrent id found"
    sys.exit(2)
(name, data) = ptp.downloadTorrent(match.group(1))
with open(os.path.join(args.destination, name), 'wb') as fh:
    fh.write(data.read())
