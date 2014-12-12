import sys
from pprint import pprint

import argparse

from ptpapi import cgapi

def do_search(args):
    cg = cgapi.CGAPI()
    cg.login()
    pprint(cg.search({'search': ' '.join(args)}))

def do_download(args):
    cg = cgapi.CGAPI()
    cg.login()
    cg.downloadTorrent(args[0])

if __name__ == '__main__':
    globals()['do_' + sys.argv[1]](sys.argv[2:])
