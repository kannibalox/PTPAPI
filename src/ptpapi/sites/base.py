from bs4 import BeautifulSoup


class BaseSiteAPI:
    Name = "BS"

    def __init__(self):
        self.baseURL = None
        self.session = None
        self.login()

    def login(self, username=None, password=None, passkey=None):
        raise NotImplementedError

    def download_to_file(self, ID, dest=None):
        raise NotImplementedError

    def find_ptp_movie(self, movie):
        raise NotImplementedError

    def bytes_to_site_size(self, byte_num):
        raise NotImplementedError

    def _httpRequest(self, url, data=None):
        html = self._request(self.baseURL + url, data)
        soup = BeautifulSoup(html, "html.parser")
        return soup

    def _request(self, url, data=None):
        return self.session.get(url, data=data).text

    def _jsonRequest(self, url, data=None):
        return self.session.get(url, data=data).json()
