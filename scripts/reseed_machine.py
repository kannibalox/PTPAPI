import sys
import re
import logging
import readline
import pickle
from urlparse import urlparse, parse_qs
from time import sleep

import ptpapi
from ptpapi import cgapi
from ptpapi import kgapi

logger = logging.getLogger(__name__)

def sizeof_fmt(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.2f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)

def findByURL(cg, kg, URL):
    ptp_id = parse_qs(urlparse(URL).query)['id'][0]
    m = ptpapi.Movie(ID=ptp_id)
    m.load_json_data()
    if 'ImdbId' not in m.data:
        logger.error('Movie has no IMDB id, cannot lookup')
        return None
    m.load_html_data()
    found_cg = None
    found_kg = None
    for t in m.Torrents:
        if 'Dead (participating in the contest)' in t.Trumpable:
            logger.info("Found dead torrent for contest")

            if found_cg is None:
                logger.debug('Searching for IMDB ID %s (PTP #%s) on CG' % (m.ImdbId, ptp_id))
                found_cg = cg.search({'search': 'tt'+str(m.ImdbId)})
            for cg_t in found_cg:
                if sizeof_fmt(int(t.Size)) == cg_t['Size'] and cg_t['Seeders'] != '0':
                    print "Found possible match at %s (%s) with %s seeders" % (cg_t['Title'], cg_t['Size'], cg_t['Seeders'])
                    cg.downloadTorrent(cg_t['ID'], name=cg_t['Title']+'.torrent')
                    break
            else:
                if found_kg is None:
                    logger.debug('Searching for IMDB ID %s (PTP #%s) on KG' % (m.ImdbId, ptp_id))
                    found_kg = kg.search({'search_type': 'imdb','search': str(m.ImdbId)})
                for kg_t in found_kg:
                    print sizeof_fmt(int(t.Size)), kg_t['Size']
                    if sizeof_fmt(int(t.Size)).replace(" ","") == kg_t['Size'] and kg_t['Seeders'] != '0':
                        print "Found possible match at %s (%s) with %s seeders" % (kg_t['Title'], kg_t['Size'], kg_t['Seeders'])
                        kg.downloadTorrent(kg_t['ID'])

def main():
    ptp = ptpapi.login()
    cg = cgapi.CGAPI()
    cg.login()
    kg = kgapi.KGAPI()
    kg.login()
    seen = pickle.load( open( 'seen.p', 'rb'))
    with open(sys.argv[1], 'r') as fh:
        for url in fh:
            ptp_id = parse_qs(urlparse(url).query)['id'][0]
            if ptp_id in seen:
                logger.error('Already seen movie %s' % ptp_id)
                continue
            else:
                findByURL(cg, kg, url)                
                seen.append(ptp_id)
                pickle.dump( seen,  open( "seen.p", "wb" ) )
                sleep(7)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
