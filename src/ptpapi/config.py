# pylint: disable=invalid-name
"""Hold config values"""
import os
import os.path

import configparser
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
config.readfp(StringIO(default))
config.read(conf_file)
