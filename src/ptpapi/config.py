# pylint: disable=invalid-name
"""Hold config values"""
import configparser
import os
import os.path

from io import StringIO


conf_file = os.path.expanduser(os.path.join("~", ".ptpapi.conf"))

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

config = configparser.ConfigParser()
config.read_file(StringIO(default))
config.read(conf_file)
