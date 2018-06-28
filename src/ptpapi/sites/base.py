class BaseSiteAPI(object):
    Name = "BS"

    def __init__(self):
        self.login()

    def login(self, username=None, password=None, passkey=None):
        raise NotImplementedError

    def download_to_file(self, ID, dest=None):
        raise NotImplementedError

    def find_ptp_movie(self, movie):
        raise NotImplementedError

    def bytes_to_site_size(self, byte_num):
        raise NotImplementedError
