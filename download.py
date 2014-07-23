import ptpapi
import argparse
import re
import os

parser = argparse.ArgumentParser(description='Download a torrent from PTP.')
parser.add_argument('-o', '--output', help='Directory to place the file in.')
parser.add_argument('url', help='The URL to get the torrent ID from.', default=os.getcwd())
args = parser.parse_args()

ptp = ptpapi.login(conf='creds.ini')
match = re.search(r'torrentid=(\d+)', args.url)
if match:
    t = ptpapi.Torrent(ID=match.group(1), load=False)
t.download_to_file(dest=args.output)