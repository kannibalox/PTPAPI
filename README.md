# PTPAPI

A small API for a mildly popular movie site. The goal was to be able to collect as much information in as few network requests as possible.

## Dependencies

* Python 3.7+
* pip

## Installation

Use of a [virtualenv](https://virtualenv.readthedocs.org/en/latest/userguide.html#usage) is highly recommended.

`pip install ptpapi`

## Configuration

Open the file `~/.ptpapi.conf` for editing, and make sure it looks like the following:

```ini
[Main]

[PTP]
ApiUser=<ApiUser>
ApiKey=<ApiKey>
```

Both values can be found in the "Security" section of your profile. This is only the minimum required configuration. See `ptpapi.conf.example` for a full-futured config file with comments.

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

This subcommand lets you search the site for movies. It can take movie and permalinks, as well as search by arbitrary parameters, and the `-d` flag allows for downloading matching torrents. For instance: 
- `ptp search year=1980-2000 taglist=sci.fi`
- `ptp search "Star Wars"`.

It can also accept URLs for torrents and collages:
- `ptp search "https://passthepopcorn.me/torrents.php?id=68148"`
- `ptp search "https://passthepopcorn.me/collages.php?id=2438"`

and regular search URLs:
- `ptp search "https://passthepopcorn.me/torrents.php?action=advanced&year=1980-2000&taglist=action"`.

As a general rule of thumb anything supported by the advanced site search will work with `ptp search`, e.g. searching `https://passthepopcorn.me/torrents.php?action=advanced&taglist=comedy&format=x264&media=Blu-ray&resolution=1080p&scene=1` is the same as `ptp search taglist=comedy format=x264 media=Blu-ray resolution=1080p scene=1`.

To work with multiple pages of results, use the `--pages <num>` flag.

There are a couple aliases to make life easier:

* `genre`, `genres`, `tags` -> `taglist`
* `name` -> `searchstr`
* `bookmarks` -> Search only your bookmarks

In addition, [Tempita](http://pythonpaste.org/tempita/) can be used for custom formatting. For instance, `ptp search --movie-format="" --torrent-format="{{UploadTime}} - {{ReleaseName}}" year=1980-2000 taglist=sci.fi grouping=no`.

Using the `-d` flag will download one torrent from each of the matched torrents (deciding which one to download is done via [filters](#filters)) to the [downloadDirectory](ptpapi.conf.example#L9).

The `-p/--pages [int]` option can be used to scrape multiple pages at once. N.B.: If any `page` parameter is in the original search query, paging will start from that page.

#### `ptp fields`

Simply list fields that can be used for the `ptp search` formatting.

### `ptp-reseed`

This script automatically matches up files to movies on PTP. It's most basic usage is `ptp-reseed <file path>`. This will search PTP for any movies matching that filename, and if it finds a match, will automatically download the torrent and add it to rtorrent. It can do some basic file manipulation if it finds a close enough match.

For instance, if you have the file `Movie.2000.mkv`, and the torrent contains `Movie (2000)/Movie.2000.mkv`, the script will try to automatically create the folder `Movie (2000)` and hard link the file inside of it before attempting to seed it.

See `ptp-reseed -h` and `ptpapi.conf.example` for more information and configuration options.

#### guessit

By default the script looks for exact matches against file names and sizes. If you'd like the name matching to be less strict, you can install the guessit library (`pip install 'guessit>=3'`), and if the filename search fails, the script will attempt to parse the movie name out of the file with guessit.

## Concepts

### Filters

Filters were designed as a way to take a full movie group, and narrow it down to a single torrent. A filter consists of multiple sub-filters, where the first sub-filter to match will download the torrent, and if not, the next sub-filter will be checked. If none of the sub-filters match, no download will occur. Filters are separate from the actual search parameters sent to the site

The full list of possible values for picking encodes is:
* `GP` or `Scene`
* `576p` or `720p` or `1080p`
* `XviD` or `x264`
* `HD` or `SD`
* `remux` or `not-remux`
* `seeded` - the number of seeds is greater than 0 (deprecated, use `seeders>0`)
* `not-trumpable` - ignore any trumpable torrents
* `unseen` - ignores all torrents if you've marked the movie as seen or rated it
* `unsnatched` - ignore all torrents unless you've never snatched one before (note that seeding counts as "snatched", but leeching doesn't)
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

## Notes

I did this mostly for fun and to serve my limited needs, which is why it's not as polished as it could be, and will probably change frequently.  Pull requests are welcomed.

### Deprecated Configuration

The new ApiUser/ApiKey system is preferred, however if you find bugs or limitations, the old cookie-based method can be used as seen here.

Open the file `~/.ptpapi.conf` for editing, and make sure it looks like the following:

```ini
[Main]

[PTP]
username=<username>
password=<password>
passkey=<passkey>
```
