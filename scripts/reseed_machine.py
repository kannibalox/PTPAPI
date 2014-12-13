import sys
import re

import ptpapi
from ptpapi import cgapi

def main():
    ptp_id = re.search(r'id=([0-9]*)', sys.argv[1]).group(1)
    ptp = ptpapi.login()
    cg = cgapi.CGAPI()
    cg.login()
    m = ptpapi.Movie(ID=ptp_id)
    print cg.search({'search': m.ImdbId})

if __name__ == '__main__':
    main()
