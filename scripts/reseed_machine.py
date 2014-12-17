import sys
import re
import logging
import readline
import pickle
from urlparse import urlparse, parse_qs
from time import sleep

import ptpapi
from ptpapi import cgapi

logger = logging.getLogger(__name__)

def sizeof_fmt(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.2f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)

def findByURL(cg, URL):
    ptp_id = parse_qs(urlparse(URL).query)['id'][0]
    m = ptpapi.Movie(ID=ptp_id)
    m.load_html_data()
    if 'ImdbId' not in m.data:
        logger.error('Movie has no IMDB id, cannot lookup')
        return None
    logger.debug('Searching for IMDB ID %s (PTP #%s) on CG' % (m.ImdbId, ptp_id))
    found_cg = cg.search({'search': 'tt'+str(m.ImdbId)})
    for t in m.Torrents:
        if 'Dead (participating in the contest)' in t.Trumpable:
            logger.info("Found dead torrent for contest")
            for cg_t in found_cg:
                if sizeof_fmt(int(t.Size)) == cg_t['Size'] and cg_t['Seeders'] != '0':
                    print "Found possible match at %s (%s) with %s seeders" % (cg_t['Title'], cg_t['Size'], cg_t['Seeders'])
                    cg.downloadTorrent(cg_t['ID'], name=cg_t['Title']+'.torrent')
    None

def main():
    ptp = ptpapi.login()
    cg = cgapi.CGAPI()
    cg.login()
    seen = pickle.load( open( 'seen.p', 'rb'))
    with open(sys.argv[1], 'r') as fh:
        for url in fh:
            ptp_id = parse_qs(urlparse(url).query)['id'][0]
            if ptp_id in seen:
                logger.error('Already seen movie %s' % ptp_id)
                continue
            else:
                findByURL(cg, url)                
                seen.append(ptp_id)
                pickle.dump( seen,  open( "seen.p", "wb" ) )
                sleep(7)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
