import sys
import re
import logging

import ptpapi
from ptpapi import cgapi

logger = logging.getLogger(__name__)

def sizeof_fmt(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.2f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)

def main():
    ptp_id = re.search(r'id=([0-9]*)', sys.argv[1]).group(1)
    ptp = ptpapi.login()
    cg = cgapi.CGAPI()
    cg.login()
    m = ptpapi.Movie(ID=ptp_id)
    m.load_html_data()
    found_cg = cg.search({'search': 'tt'+str(m.ImdbId)})
    for t in m.Torrents:
        if 'Dead (participating in the contest)' in t.Trumpable:
            logger.info("Found dead torrent for contest")
            for cg_t in found_cg:
                if sizeof_fmt(int(t.Size)) == cg_t['Size'] and cg_t['Seeders'] != '0':
                    print "Found possible match at %s (%s) with %s seeders" % (cg_t['Title'], cg_t['Size'], cg_t['Seeders'])
                    cg.downloadTorrent(cg_t['ID'], name=cg_t['Title']+'.torrent')

if __name__ == '__main__':
    main()
