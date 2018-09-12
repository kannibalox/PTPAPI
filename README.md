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

Filters were designed as a way to take a full movie group, and narrow it down to a single torrent. A filter consists of multiple sub-filters, where the first sub-filter to match will download the torrent, and if not, the next sub-filter will be checked. If none of the sub-filters match, no download will occur. 

The full list of possible values for picking encodes is:
* `GP` or `Scene`
* `576p` or `720p` or `1080p`
* `XviD` or `x264`
* `HD` or `SD`
* `Remux`
* `seeded` - the number of seeds is greater than 0 (deprecated, use `seeders>0`)
* `not-trumpable` - ignore any trumpable torrents
* `unseen` - ignores all torrents if you've marked the movie as seen or rated it
* `unsnatched` - ignore all torrents unless you've never snatched one before (note that seeding counts as "snatched", but leeching doesn't
There are also values that allow for simple comparisons, e.g. `size>1400M`.
* `seeders`
* `size`

Note that it's possible to have two incompatible values, e.g. `GP` and `Scene`, but this simply means the sub-filter won't ever match a torrent, and will always be skipped over.

The possible values for sorting are:
* `most recent` (the default if none are specified)
* `smallest`
* `most seeders`
* `largest`

#### Examples

For instance, the filter `smallest GP,720p scene,largest` would attempt to download the smallest GP. If there are no GPs, it will try to find a 720p scene encode. If it can't find either of those, it will just pick the largest torrent available.

As another example, if you wanted to filter for encodes that are less than 200MiB with only one seeder, you could use `seeders=1 size<200M`.

## Usage

The three CLI commands are `ptp`, `ptp-reseed`, and `ptp-bookmarks`

### `ptp`

This is a generally utility to do various things inside PTP. As of right now it can download files, search the site for movies, and list message in your inbox.

See `ptp help` for more information.

#### `ptp inbox`

A small utility to read messages in your inbox. No reply capability currently.

#### `ptp download`

An alias for `ptp-search -d`

#### `ptp search`

This subcommand lets you search the site for movies. It can take movie and permalinks, as well as search by arbitrary parameters. For instance, `ptp search year=1980-2000 taglist=sci.fi` or `ptp search "Star Wars"`. It can also accept URLs for torrents and collages, e.g. `ptp search "https://passthepopcorn.me/torrents.php?id=68148"` or `ptp search https://passthepopcorn.me/collages.php?id=2438`, and regular search URLs, e.g. `https://passthepopcorn.me/torrents.php?action=advanced&year=1980-2000&taglist=action`.

There are a couple aliases to make life easier:

* `genre`, `genres`, `tags` -> `taglist`
* `name` -> `searchstr`
* `bookmarks` -> Search only your bookmarks

In addition, [Tempita](http://pythonpaste.org/tempita/) can be used for custom formatting. For instance, `ptp search --movie-format="" --torrent-format="{{UploadTime}} - {{ReleaseName}}" year=1980-2000 taglist=sci.fi grouping=no`.

Using the `-d` flag will download one torrent from each of the matched torrents (via filters) to the [downloadDirectory](ptpapi.conf.example#L9).

### `ptp-reseed`

This script automatically matches up files to movies on PTP. It's most basic usage is `ptp-reseed <file path>`. This will search PTP for any movies matching that filename, and if it finds a match, will automatically download the torrent and add it to rtorrent. It can do some basic file manipulation if it finds a close enough match.

For instance, if you have the file `Movie.2000.mkv`, and the torrent contains `Movie (2000)/Movie.2000.mkv`, the script will try to automatically create the folder `Movie (2000)` and hard link the file inside of it before attempting to seed it.

See `ptp-reseed -h` and `ptpapi.conf.example` for more information and configuration options.

#### guessit

By default the script looks for exact matches against file names and sizes. If you'd like the name matching to be less strict, you can install the guessit library (`pip install guessit`), and if the filename search fails, the script will attempt to parse the movie name out of the file with guessit.

### Notes

I did this mostly for fun and to serve my limited needs, which is why it's not as polished as it could be, and will probably change frequently.  Pull requests are welcomed.
