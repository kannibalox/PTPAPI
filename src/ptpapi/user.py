"""Represent a user"""
import re

from bs4 import BeautifulSoup as bs4  # pylint: disable=import-error

from .movie import Movie
from .session import session
from .util import snarf_cover_view_data


class User:
    """A primitive class to represent a user"""

    def __init__(self, ID):
        # Requires an ID, as searching by name isn't exact on PTP
        self.ID = ID  # pylint: disable=invalid-name

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "<ptpapi.User ID %s>" % self.ID

    def bookmarks(self, search_terms=None):
        """Fetch a list of movies the user has bookmarked

        :rtype: array of Movies"""
        search_terms = search_terms or {}
        search_terms.update({"userid": self.ID})
        req = session.base_get("bookmarks.php", params=search_terms)
        movies = []
        for movie in snarf_cover_view_data(req.text):
            movies.append(Movie(data=movie))
        return movies

    def ratings(self):
        """Fetch a list of rated movies

        :rtype: array of tuples with a Movie and a rating out of 100"""
        soup = bs4(
            session.base_get(
                "user.php", params={"id": self.ID, "action": "ratings"}
            ).text,
            "html.parser",
        )
        ratings = []
        for row in soup.find(id="ratings_table").tbody.find_all("tr"):
            movie_id = re.search(r"id=(\d+)", row.find(class_="l_movie")["href"]).group(
                1
            )
            rating = row.find(id="user_rating_%s" % movie_id).text.rstrip("%")
            ratings.append((movie_id, rating))
        return ratings

    def __parse_stat(self, stat_line):
        stat, _, value = stat_line.partition(":")
        stat = stat.title().replace(" ", "").strip()
        value = re.sub(r"\t.*", "", value).replace("[View]", "").strip()
        return stat, value

    def stats(self):
        """
        Return all stats associated with a user

        :rtype: A dictionary of stat names and their values, both in string format.
        """
        soup = bs4(
            session.base_get("user.php", params={"id": self.ID}).text, "html.parser"
        )
        stats = {}
        for li in soup.find("span", text="Stats").parent.parent.find_all("li"):
            stat, value = self.__parse_stat(li.text)
            stats[stat] = value
        for li in soup.find("span", text="Personal").parent.parent.find_all("li"):
            stat, value = self.__parse_stat(li.text)
            if value:
                stats[stat] = value
        for li in soup.find("span", text="Community").parent.parent.find_all("li"):
            stat, value = self.__parse_stat(li.text)
            if stat == "Uploaded":
                match = re.search(r"(.*) \((.*)\)", value)
                stats["UploadedTorrentsWithDeleted"] = match.group(1)
                value = match.group(2)
                stat = "UploadedTorrents"
            elif stat == "Downloaded":
                stat = "DownloadedTorrents"
            elif stat == "SnatchesFromUploads":
                match = re.search(r"(.*) \((.*)\)", value)
                stats["SnatchesFromUploadsWithDeleted"] = match.group(1)
                value = match.group(2)
            elif stat == "AverageSeedTime(Active)":
                stat = "AverageSeedTimeActive"
            stats[stat] = value
        return stats


class CurrentUser(User):
    """Defines some additional methods that only apply to the logged in user."""

    def __init__(self, ID):
        self.new_messages = 0
        super().__init__(ID)

    def archive_container(self, ID):
        """Fetch info about a containers from the archive project

        :returns: A list of dictionaries"""
        torrents = []
        params = {"action": "container", "UserID": self.ID, "containerid": ID}
        soup = bs4(session.base_get("archive.php", params=params).text, "html.parser")
        headers = [
            h.text
            for h in soup.find(class_="table").find("thead").find("tr").find_all("th")
        ]
        rows = soup.find(class_="table").find("tbody").find_all("tr")
        for r in rows:
            # Get as much info as possible from the pages
            row_dict = dict(zip(headers, [f.text for f in r.find_all("td")]))
            # Also add in a Torrent object for creating torrent objects
            if "Torrent Deleted" not in row_dict["Torrent"]:
                row_dict["TorrentId"] = re.search(
                    r"torrentid=([0-9]*)", r.find_all("td")[0].find("a")["href"]
                ).group(1)
        return torrents

    def archive_containers(self):
        """Fetch a list of containers from the archive project

        :returns: A list of dictionaries"""
        containers = []
        soup = bs4(session.base_get("archive.php").text, "html.parser")
        for row in soup.find(class_="table").find("tbody").find_all("tr"):
            cont = {
                "name": row[0].text,
                "link": r[0].find("a")["href"],
                "size": ptpapi.util.human_to_bytes(r[1].text),
                "max_size": ptpapi.util.human_to_bytes(r[2].text),
                "last_fetch": r[3].text,  # TODO: convert this to actual time object
            }
            for field in row:
                if field.find("label"):
                    l = field.find("label")
                    cont[l["title"].lower()] = int(l.text.replace(",", ""))
            containers.append(cont)
        return containers

    def __parse_new_messages(self, soup):
        """Parse the number of messages from a soup of html"""
        msgs = 0
        if soup.find(class_="alert-bar"):
            for alert in soup.find(class_="alert-bar"):
                match = re.search(r"You have (\d+) new message", alert.text)
                if match:
                    msgs = match.group(1)
        return msgs

    def get_new_messages(self):
        """Update the number of messages"""
        soup = bs4(session.base_get("inbox.php").text, "html.parser")
        self.new_messages = self.__parse_new_messages(soup)
        return self.new_messages

    def inbox(self, page=1):
        """Fetch a list of messages from the user's inbox
        Incidentally update the number of messages"""
        soup = bs4(
            session.base_get("inbox.php", params={"page": page}).text, "html.parser"
        )

        self.new_messages = self.__parse_new_messages(soup)

        for row in soup.find(id="messageformtable").tbody.find_all("tr"):
            yield {
                "Subject": row.find_all("td")[1].text.encode("UTF-8").strip(),
                "Sender": row.find_all("td")[2].text,
                "Date": row.find_all("td")[3].span["title"],
                "ID": re.search(r"id=(\d+)", row.find_all("td")[1].a["href"]).group(1),
                "Unread": bool("inbox-message--unread" in row["class"]),
            }

    def inbox_conv(self, conv_id):
        """Get a specific conversation from the inbox"""
        soup = bs4(
            session.base_get(
                "inbox.php", params={"action": "viewconv", "id": conv_id}
            ).text,
            "html.parser",
        )
        messages = []
        for msg in soup.find_all("div", id=re.compile("^message"), class_="forum-post"):
            message = {}
            message["Text"] = msg.find("div", class_="forum-post__body").text.strip()
            username = msg.find("strong").find("a", class_="username")
            if username is None:
                message["User"] = "System"
            else:
                message["User"] = username.text.strip()
            message["Time"] = msg.find("span", class_="time").text.strip()
            messages.append(message)
        return {
            "Subject": soup.find("h2", class_="page__title").text,
            "Message": messages,
        }

    def remove_snatched_bookmarks(self):
        """Remove snatched bookmarks"""
        session.base_post("bookmarks.php", data={"action": "remove_snatched"})

    def remove_seen_bookmarks(self):
        """Remove seen bookmarks"""
        session.base_post("bookmarks.php", data={"action": "remove_seen"})

    def remove_uploaded_bookmarks(self):
        """Remove uploads bookmarks"""
        session.base_post("bookmarks.php", data={"action": "remove_uploaded"})

    def hnr_zip(self):
        """Download the zip file of all HnRs"""
        zip_file = session.base_get("snatchlist.php", params={"action": "hnrzip"})
        if zip_file.headers["Content-Type"] == "application/zip":
            return zip_file
        else:
            return None
