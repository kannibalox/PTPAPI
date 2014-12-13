import sys
import logging
from pprint import pprint

import argparse

from ptpapi import ptpapi

def do_search(args):
    terms = {}
    for arg in args:
        term = arg.partition('=')
        if not term[2]:
            terms['searchstr'] = term[0]
        else:
            terms[term[0]] = term[2]
    api = ptpapi.login(**ptpapi.util.creds_from_conf(args.cred))
    
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extensible command line utility for PTP')
    parser.add_argument('--debug', help='Print lots of debugging statements', action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument('-v', '--verbose', help='Be verbose', action="store_const", dest="loglevel", const=logging.INFO)
    parser.add_argument('-c', '--cred', help='Credential file', default="creds.ini")
    globals()['do_' + sys.argv[1]](sys.argv[2:])
