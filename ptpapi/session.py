import logging
from time import time, sleep

import requests

from config import config

logger = logging.getLogger(__name__)


class TokenSession(requests.Session):
    """Allows rate-limiting requests to the site"""
    def __init__(self, tokens, fill_rate):
        """tokens is the total tokens in the bucket. fill_rate is the
        rate in tokens/second that the bucket will be refilled."""
        super(TokenSession, self).__init__()
        self.capacity = float(tokens)
        self._tokens = float(tokens)
        self.consumed_tokens = 0
        self.fill_rate = float(fill_rate)
        self.timestamp = time()

    def consume(self, tokens):
        """Consume tokens from the bucket. Returns True if there were
        sufficient tokens otherwise False."""
        self.get_tokens()
        if tokens <= self.tokens:
            self._tokens -= tokens
            self.consumed_tokens += tokens
            logger.debug("Consuming %i token(s)." % tokens)
        else:
            return False
        return True

    def request(self, *args, **kwargs):
        while not self.consume(1):
            logger.debug("Waiting for token bucket to refill...")
            sleep(1)
        return super(TokenSession, self).request(*args, **kwargs)

    def get_tokens(self):
        if self._tokens < self.capacity:
            now = time()
            delta = self.fill_rate * (now - self.timestamp)
            self._tokens = min(self.capacity, self._tokens + delta)
            self.timestamp = now
        return self._tokens

    tokens = property(get_tokens)

    def base_get(self, url_path, *args, **kwargs):
        return self.get(config.get('Main', 'baseURL') + url_path, *args, **kwargs)

    def base_post(self, url_path, *args, **kwargs):
        return self.post(config.get('Main', 'baseURL') + url_path, *args, **kwargs)


logger.debug("Initializing token session")
# If you change this and get in trouble, don't blame me
session = TokenSession(3, 0.5)
session.headers.update({"User-Agent": "Wget/1.13.4"})
