# Changelog

All notable changes to this integration are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each release is also on the
GitHub releases page with the same notes.

## [Unreleased]

### Added

- Weekly Dependabot updates for the GitHub Actions the workflows use.

## [0.2.2] - 2026-11-10

### Removed

- The Measure now button. Its command is not verified on a real probe, so the integration
  no longer sends it. Read firmware version and Identify are unchanged.

## [0.2.1] - 2026-11-07

First public release.

### Added

- Reads an iopool EcO pool and spa water probe locally over Bluetooth, directly or through
  ESPHome Bluetooth proxies. No cloud.
- pH, ORP and temperature from the probe's own broadcasts, plus raw conductivity and battery.
- Calibration from your own reference readings (see "Calibration" in the README).
- Buttons that connect briefly: read the firmware version, and identify the probe with a beep.

[Unreleased]: https://github.com/pete-jorgensen/iopool-ble/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/pete-jorgensen/iopool-ble/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/pete-jorgensen/iopool-ble/releases/tag/v0.2.1
