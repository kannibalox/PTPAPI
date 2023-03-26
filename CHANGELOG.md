# Changelog

## [Unreleased]

### Added
- Utility script for downloading and running archiver.py
- [`tinycron`](https://github.com/bcicen/tinycron) has been added to
  docker to allow for simple cron-like containers
- `ptp-reseed`
  - simple file downloading: use `file://<path>` with `--client`
  - Add flag for pre-hash-checking: `--hash-check`
  - Add flag for changing the path of an existing incomplete torrent: `--overwrite-incomplete`

## [0.8.0] - 2023-03-18

### Fixed
- Size comparisons in filters were be compared case-sensitively

### Changed
- Cleaned up and documented `ptp-reseed-machine` for general usage

### Added
- Add `ReseedMachine -> ignoreTitleResults` config setting to allow
  filtering out trackers from the title search
- Allow reading config from multiple locations: `~/.ptpapi.conf`,
  `~/.config/ptpapi.conf`, `~/.config/ptpapi/ptpapi.conf`
- Config values can now be loaded from environment variables
- Added a changelog
- Created dockerfile

[Unreleased]: https://github.com/kannibalox/pyrosimple/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/kannibalox/pyrosimple/compare/v0.7.2...v0.8.0
