# PTPAPI

A small API for a mildly popular movie site. The goal was to be able to collect as much information in as few network requests as possible.

## Dependencies

* Python 2.7
 * BeautifulSoup 4
 * pyroscope
 * requests
* PIP

## Installation

`pip install https://github.com/kannibalox/PTPAPI/archive/master.zip`

Use [virtualenv](https://virtualenv.readthedocs.org/en/latest/userguide.html#usage) if you don't have root access.

## Configuration

Open the file `~/.ptpapi.conf` for editing, and make sure it looks like the following:

```ini
[Main]

[PTP]
username=<username>
password=<password>
passkey=<passkey>
```

This is only the minimum required configuration. See `ptpapi.conf.example` for a full-futured config file with comments.

## Concepts

### Filters

Filters were designed as a way to take a full movie group, and narrow it down to a single torrent. A filter consists of multiple subfilters, where the first subfilter to match will download the torrent, and if not, the next subfilter will be checked. If none of the subfilters match, no download will occur. For instance, the filter `smallest GP,720p scene,largest` would attempt to download the smallest GP. If there are no GPs, it will try to find a 720p scene encode. If it can't find either of those, it will just pick the largest torrent available.

The full list of possible values for picking encodes is:
* `GP`
* `Scene`
* `576p` or `720p` or `1080p`
* `HD` or `SD`
* `Remux`

Note that it's possible to have two incompatible values, e.g. `GP` and `Scene`, but this simply means the subfilter won't ever match a torrent, and it will always be skipped over.

The possible values for sorting are:
* `most recent`
* `smallest`
* `seeded` (the number of seeds)
* `largest`

## Usage

The three CLI commands are `ptp`, `ptp-reseed`, and `ptp-bookmarks`

### `ptp`

This is a generally utility to do various things inside PTP. As of right now it can download files, search the site for movies, and list message in your inbox.

See `ptp help` for more information.

#### `ptp search`

This subcommand lets you search the site for movies. It can take movie and permalinks, as well as search by arbitrary parameters. For instance, `ptp search year=1980-2000 taglist=sci.fi`.

There are a couple aliases to make life easier:

* `genre`, `genres`, `tags` -> `taglist`
* `name` -> `searchstr`

In addition, [Tempita](http://pythonpaste.org/tempita/) can be used for custom formatting. For instance, `ptp search --movie-format="" --torrent-format="{{UploadTime}} - {{ReleaseName}}" year=1980-2000 taglist=sci.fi grouping=no`

### `ptp-reseed`

This script automatically matches up files to movies on PTP. It's most basic usage is `ptp-reseed <file path>`. This will search PTP for any movies matching that filename, and if it finds a match, will automatically download the torrent and add it to rtorrent. It can do some basic file manipulation if it finds a close enough match.

For instance, if you have the file `Movie.2000.mkv`, and the torrent contains `Movie (2000)/Movie.2000.mkv`, the script will try to automatically the folder `Movie (2000)` and hard link the file inside of it before attempting to seed it.

See `ptp-reseed -h` for more information

#### guessit

By default the script looks for exact matches against file names and sizes. If you'd like the name matching to be less strict, you can install the guessit library (`pip install guessit`), and if the filename search fails, the script will attempt to parse the movie name out of the file and search by that.

### `ptp-bookmarks`

*This script will attempt to remove all snatched bookmarks. You have been warned.*

This can download bookmarked torrents based on a human language filter. The basic syntax looks like `ptp-bookmarks -f <filter>`.


See `ptp-bookmarks --help` for more information.

### Notes

I did this mostly for fun and to serve my limited needs, which is why it's not as polished as it could be, and will probably change frequently.  Pull requests are welcomed.
