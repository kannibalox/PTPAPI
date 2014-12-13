import os
import os.path
import ConfigParser

confFile = os.path.join(os.environ['HOME'], '.ptpapi.conf')

defaults = {'baseURL': 'https://tls.passthepopcorn.me/',
            'cookiesFile': 'cookies.txt'}
config = ConfigParser.ConfigParser(defaults)
config.read(confFile)
