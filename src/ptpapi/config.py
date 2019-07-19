# pylint: disable=invalid-name
"""Hold config values"""
import os
import os.path

from six.moves import configparser
from six import StringIO

conf_file = os.path.join(os.environ["HOME"], ".ptpapi.conf")

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
