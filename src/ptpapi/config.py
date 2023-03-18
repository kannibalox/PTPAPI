# pylint: disable=invalid-name
"""Hold config values"""
import configparser
import os

from io import StringIO
from pathlib import Path


conf_files = [
    Path(p)
    for p in ["~/.ptpapi.conf", "~/.config/ptpapi.conf", "~/.config/ptpapi/ptpapi.conf"]
]

default = """
[Main]
baseURL=https://passthepopcorn.me/
cookiesFile=~/.ptp.cookies.txt
downloadDirectory=.
filter=
retry=False

[Reseed]
action=hard
findBy=filename,title
"""

env_prefix = "PTPAPI_"
env_keys = {
    "BASEURL": ("Main", "baseURL"),
    "COOKIESFILE": ("Main", "cookiesFile"),
    "FILTER": ("Main", "filter"),
    "RETRY": ("Main", "retry"),
    "APIUSER": ("PTP", "ApiUser"),
    "APIKEY": ("PTP", "ApiKey"),
    "RESEED_ACTION": ("Reseed", "action"),
    "RESEED_FINDBY": ("Reseed", "findBy"),
    "ARCHIVE_CONTAINER_NAME": ("PTP", "archiveContainerName"),
    "ARCHIVE_CONTAINER_SIZE": ("PTP", "archiveContainerSize"),
    "ARCHIVE_MAX_STALLED": ("PTP", "archiveContainerMaxStalled"),
    "PROWLARR_URL": ("Prowlarr", "url"),
    "PROWLARR_API_KEY": ("Prowlarr", "api_key"),
}


config = configparser.ConfigParser()
config.read_file(StringIO(default))
for c in conf_files:
    if c.expanduser().exists():
        config.read(c.expanduser())
        break
else:
    raise ValueError(
        f"Config file not found in any of the following paths: {conf_files!r}"
    )

for key, section in env_keys.items():
    if os.getenv(env_prefix + key) is not None:
        config.set(section[0], section[1], os.getenv(env_prefix + key))
