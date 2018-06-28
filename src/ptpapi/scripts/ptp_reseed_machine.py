#!/usr/bin/env python
import logging
import argparse
from urlparse import urlparse, parse_qs

import ptpapi
from ptpapi.sites import CGAPI
from ptpapi.sites import KGAPI

class DownloadFoundException(Exception):
    pass

def main():
    parser = argparse.ArgumentParser(description='Attempt to find torrents to reseed on PTP from other sites')
    parser.add_argument('-i', '--id', help='Only full PTP links for now', nargs='*')
    parser.add_argument('--debug', help='Print lots of debugging statements',
                        action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument('-v', '--verbose', help='Be verbose', action="store_const", dest="loglevel", const=logging.INFO)
    parser.add_argument('-l', '--limit', help="Limit need-for-seed results to N movies", default=100, type=int)
    parser.add_argument('-s', '--search', help="Allow filtering the need-for-seed results", default=None)
    parser.add_argument('-r', '--required-remote-seeds', help="The number of seeds required on the remote site", default=1, type=int)
    parser.add_argument('-m', '--min-ptp-seeds', help="Set the minimum number of seeds before a reseed will happen", default=0, type=int)
    args = parser.parse_args()
    
    logging.basicConfig(level=args.loglevel)
    logger = logging.getLogger('reseed-machine')

    logger.info("Logging into PTP")
    ptp = ptpapi.login()
    logger.info("Logging into CG")
    cg = CGAPI()
    logger.info("Logging into KG")
    kg = KGAPI()
    sites = [cg, kg]
    
    if args.id:
        movies = args.id
    else:
        filters = {}
        if args.search:
            for arg in args.search.split(','):
                filters[arg.split('=')[0]] = arg.split('=')[1]
        movies = [t['Link'] for t in ptp.need_for_seed(filters)][:args.limit]
    
    for i in movies:
        ptp_movie = None
        if '://passthepopcorn.me' in i:
            parsed_url = parse_qs(urlparse(i).query)
            ptp_movie = ptpapi.Movie(ID=parsed_url['id'][0])

        if ptp_movie is None:
            logger.error("Could not figure out ID '{0}'".format(i))
        else:
            try:
                ptp_movie['ImdbId']
            except KeyError:
                logger.warn("ImdbId not found from '{0}', skipping".format(i))
                continue
            find_match(ptp_movie, sites,
                       min_seeds=args.min_ptp_seeds,
                       remote_seeds=args.required_remote_seeds)

def find_match(ptp_movie, sites, min_seeds=0, remote_seeds=0):
    logger = logging.getLogger(__name__)
    for site in sites:
        for torrent in site.find_ptp_movie(ptp_movie):
            for ptp_torrent in ptp_movie['Torrents']:
                logger.debug(u'Comparing humanized size {0} to {1} and seeds {2} <= {3} and {4} >= {5}'.format(
                    site.bytes_to_site_size(ptp_torrent['Size']),
                    torrent['BinaryHumanSize'],
                    ptp_torrent['Seeders'],
                    min_seeds,
                    torrent['Seeders'],
                    remote_seeds))
                if (site.bytes_to_site_size(ptp_torrent['Size']) == torrent['BinaryHumanSize']
                    and int(torrent['Seeders']) >= remote_seeds
                    and int(ptp_torrent['Seeders']) <= min_seeds):

                    logger.info(u'Downloading torrent {0} from {1}'.format(torrent['ID'], site))
                    site.download_to_file(torrent['ID'])
                    break

if __name__ == '__main__':
    main()
