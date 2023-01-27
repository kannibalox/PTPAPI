import html
import json
import math
import re
import urllib

from bs4 import BeautifulSoup as bs4

from ptpapi.error import PTPAPIException


def raise_for_cloudflare(text):
    """Raises an exception if a CloudFlare error page is detected

    :param text: a raw html string"""
    soup = bs4(text, "html.parser")
    if soup.find(class_="cf-error-overview") is not None:
        msg = "-".join(soup.find(class_="cf-error-overview").get_text().splitlines())
        raise PTPAPIException("Encountered Cloudflare error page: ", msg)


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


# Adapted from https://gist.github.com/leepro/9694638

SYMBOLS = {
    "customary": ("B", "K", "M", "G", "T", "P", "E", "Z", "Y"),
    "customary_ext": (
        "byte",
        "kilo",
        "mega",
        "giga",
        "tera",
        "peta",
        "exa",
        "zetta",
        "iotta",
    ),
    "iec": ("Bi", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi"),
    "iec_b": ("BiB", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"),
    "iec_ext": ("byte", "kibi", "mebi", "gibi", "tebi", "pebi", "exbi", "zebi", "yobi"),
}


def human_to_bytes(s):
    """
    Attempts to guess the string format based on default symbols
    set and return the corresponding bytes as an integer.
    When unable to recognize the format ValueError is raised.

      >>> human2bytes('0 B')
      0
      >>> human2bytes('1 K')
      1024
      >>> human2bytes('1 M')
      1048576
      >>> human2bytes('1 Gi')
      1073741824
      >>> human2bytes('1 tera')
      1099511627776

      >>> human2bytes('0.5kilo')
      512
      >>> human2bytes('0.1  byte')
      0
      >>> human2bytes('1 k')  # k is an alias for K
      1024
      >>> human2bytes('12 foo')
      Traceback (most recent call last):
          ...
      ValueError: can't interpret '12 foo'
    """
    try:
        return int(s)
    except ValueError:
        pass
    s = s.replace(",", "")
    init = s
    num = ""
    while s and s[0:1].isdigit() or s[0:1] == ".":
        num += s[0]
        s = s[1:]
    num = float(num)
    letter = s.strip()
    for _, sset in SYMBOLS.items():
        if letter in sset:
            break
    else:
        if letter == "k":
            # treat 'k' as an alias for 'K' as per: http://goo.gl/kTQMs
            sset = SYMBOLS["customary"]
            letter = letter.upper()
        else:
            raise ValueError("can't interpret %r" % init)
    prefix = {sset[0]: 1}
    for i, sval in enumerate(sset[1:]):
        prefix[sval] = 1 << (i + 1) * 10
    return int(num * prefix[letter])


def snarf_cover_view_data(text, key=rb"coverViewJsonData\[\s*\d+\s*\]"):
    """Grab cover view data directly from an html source
    and parse out any relevant infomation we can

    :param text: a raw html string
    :rtype: a dictionary of movie data"""
    data = []
    for json_data in re.finditer(key + rb"\s*=\s*({.*});", text, flags=re.DOTALL):
        data.extend(json.loads(json_data.group(1).decode())["Movies"])
        for movie in data:
            movie["Title"] = html.unescape(movie["Title"])
            movie["Torrents"] = []
            for group in movie["GroupingQualities"]:
                for torrent in group["Torrents"]:
                    soup = bs4(torrent["Title"], "html.parser")
                    if len(soup.a.text.split("/")) < 4:
                        continue
                    (
                        torrent["Codec"],
                        torrent["Container"],
                        torrent["Source"],
                        torrent["Resolution"],
                    ) = [item.strip() for item in soup.a.text.split("/")[0:4]]
                    torrent["GoldenPopcorn"] = (
                        soup.contents[0].string.strip(" ") == "\u10047"
                    )  # 10047 = Unicode GP symbol pylint: disable=line-too-long
                    if "title" not in soup.a:
                        continue
                    torrent["ReleaseName"] = soup.a["title"].split("\n")[-1]
                    match = re.search(
                        r"torrents.php\?id=(\d+)&torrentid=(\d+)", soup.a["href"]
                    )
                    torrent["Id"] = match.group(2)
                    movie["Torrents"].append(torrent)
    return data


def find_page_range(text) -> int:
    """From a full HTML page, try to find the number of available
    pages."""
    # Try loading as a big JSON
    try:
        data = json.loads(text)
        return math.ceil(int(data["TotalResults"]) / len(data["Movies"]))
    except json.decoder.JSONDecodeError:
        pass
    # Try parsing pagination infromation from HTML
    soup = bs4(text, "html.parser")
    url = soup.select("a.pagination__link--last")[0]["href"]
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return int(qs["page"][0])
