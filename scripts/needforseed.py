#!/bin/env python
# Search for torrents from other sites to reseed on ptp

import argparse

import ptpapi

def main():
    ptp = ptpapi.login(conf="creds.ini")
    torrents = ptp.need_for_seed()

if __name__ == '__main__':
    main()
