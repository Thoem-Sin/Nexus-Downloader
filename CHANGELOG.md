# Changelog

All notable changes to Nexus Downloader are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [8.0.0] - 2026-03-29

### Added
- ✨ New glassmorphic UI design with smooth animations
- 🎨 Dark and Light theme support with real-time switching
- 📺 Channel scraper panel for batch downloading playlists and channels
- 🔒 Enhanced license validation system with offline grace period
- 🔄 Auto-updater with background update checking
- ⚙️ Advanced settings dialog for proxy configuration and download customization
- 📊 Real-time download statistics and progress tracking
- 🎯 Smart queue management with pause/resume functionality
- 🌐 Graceful fallback UI when internet is unavailable
- 📝 Build documentation and compilation guide
- 🎭 Multiple UI themes and animations

### Changed
- 🔄 Completely refactored UI architecture using PySide6
- 📈 Improved download worker with better error handling
- 🎯 Enhanced format panel with better layout and UX
- 💾 Settings now persisted in JSON format
- 📦 Modularized codebase into widgets and components

### Fixed
- 🐛 Fixed file naming conflicts with special characters
- 🔧 Improved memory usage during large batch downloads
- 🌐 Better handling of network timeouts
- ✅ Resolved icon rendering issues on different platforms
- 🔐 Fixed license validation edge cases

### Removed
- ❌ Legacy Tkinter UI (replaced with PySide6)
- ❌ Old configuration format (migrated to JSON)

### Security
- 🔒 HTTPS-only validation server communication
- 🛡️ Added license revocation checks
- 🔐 Improved credential handling

---

## [7.5.1] - 2026-02-15

### Fixed
- 🐛 Fixed crash when downloading videos with missing metadata
- 🔧 Improved thread safety in download queue
- 🌐 Better error messages for network failures

---

## [7.5.0] - 2026-02-01

### Added
- 🎵 Support for more audio formats (opus, vorbis)
- 📊 Download statistics dashboard
- 🔍 Improved URL validation

### Fixed
- 🐛 Fixed duplicate queue entries
- 🔧 Improved file permission handling on Linux

---

## [7.0.0] - 2025-12-10

### Added
- 🎥 Multi-platform support (YouTube, Twitch, and 500+ others)
- 📁 Batch download from playlists
- ⚙️ Customizable quality settings
- 🎨 Basic UI improvements

### Changed
- 📦 Migrated to yt-dlp for better compatibility

---

## Legend

- ✨ New features
- 🔄 Changes
- 🐛 Bug fixes
- 🔒 Security improvements
- ❌ Deprecations/Removals
- 📈 Performance improvements
- 🎨 UI/Design updates
- 📝 Documentation
- 🔧 Maintenance
- ⚙️ Configuration changes

---

## Unreleased

### Planned for 8.1.0
- [ ] Plugin system for custom video sources
- [ ] Cloud storage integration (Google Drive, Dropbox)
- [ ] WebRTC stream recording
- [ ] Mobile app companion
- [ ] Subtitle download and burning

### Under Consideration
- [ ] Native macOS and Linux builds (besides Python)
- [ ] Multi-language UI support
- [ ] Custom subtitle rendering
- [ ] Integration with video editors
