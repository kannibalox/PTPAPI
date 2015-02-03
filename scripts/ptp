#!/bin/env python
import sys
import logging
from pprint import pprint

import argparse

import ptpapi

def do_search(args):
    terms = {}
    for arg in args:
        term = arg.partition('=')
        if not term[2]:
            terms['searchstr'] = term[0]
        else:
            terms[term[0]] = term[2]
    api = ptpapi.login()
    for m in api.search(terms):
        print "%s (%s) - %s - [%s] - [PTP %s, IMDB %s]" % (m.Title, m.Year, ', '.join([d['Name'] for d in m.Directors]), '/'.join(m.Tags), m.GroupId, (m.ImdbId or '0'))
        for t in m.Torrents:
            print "- %s - %s/%s/%s/%s - %s/%s/%s" % (t.ReleaseName, t.Codec, t.Container, t.Source, t.Resolution, t.Snatched, t.Seeders, t.Leechers)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extensible command line utility for PTP')
    parser.add_argument('--debug', help='Print lots of debugging statements', action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument('-v', '--verbose', help='Be verbose', action="store_const", dest="loglevel", const=logging.INFO)
    parser.add_argument('-c', '--cred', help='Credential file', default="creds.ini")
    globals()['do_' + sys.argv[1]](sys.argv[2:])
