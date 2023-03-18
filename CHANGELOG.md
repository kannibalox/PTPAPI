# Changelog

## [Unreleased]

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

[Unreleased]: https://github.com/kannibalox/pyrosimple/compare/v0.7.2...HEAD
