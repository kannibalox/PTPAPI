# pylint: disable=invalid-name
"""Hold config values"""
import os
import os.path
import StringIO
import ConfigParser

confFile = os.path.join(os.environ['HOME'], '.ptpapi.conf')

default = """
[Main]
baseURL=https://passthepopcorn.me/
cookiesFile=~/.ptp.cookies.txt
downloadDirectory=.
filter=

[Reseed]
action=hard
findBy=filename,title
"""
config = ConfigParser.ConfigParser()
config.readfp(StringIO.StringIO(default))
config.read(confFile)
