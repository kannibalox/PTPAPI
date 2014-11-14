#!/usr/env python
# Downloads a number of bookmarks to a specified directory
import argparse
import os

from ptpapi import ptpapi

def main():
    parser = argparse.ArgumentParser(description="Download a number of bookmarks")
    parser.add_argument('-d','--destination', help="The destination folder", default=os.getcwd())
    parser.add_argument('-n','--number', help='Number of torrents to download', default=1, type=int)
    parser.add_argument('-f', '--filters', help='A string filter of the torrents to download', required=True)
    parser.add_argument('-c', '--cred', help='Credential file', default="creds.ini")

    args = parser.parse_args()

    api = ptpapi.login(**ptpapi.util.creds_from_conf(args.cred))
    try:
        api.remove_snatched_bookmarks()
        bmks = api.current_user().bookmarks()
        for b in bmks[0:args.number]:
            b.load_json_data()
            best = ptpapi.best_match(b, args.filters)
            if best:
                best.download_to_file(dest=args.destination)
    finally:
        api.logout()
                

if __name__ == '__main__':
    main()
