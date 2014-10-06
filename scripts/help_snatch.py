import ptpapi

ptp = ptpapi.PTPAPI()
ptp.login()
for torrent in ptp.findTorrentLinks(ptp.unreadPostsInThread(16446)):
    filename, data = ptp.downloadTorrent(torrent)
    with open(filename, 'wb') as fh:
        fh.write(data.read())
