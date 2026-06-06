# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3](https://github.com/verygoodplugins/robinhood-mcp/compare/v0.1.2...v0.1.3) (2026-04-22)


### Performance Improvements

* slim get_positions response to reduce context window bloat ([#13](https://github.com/verygoodplugins/robinhood-mcp/issues/13)) ([d0849f3](https://github.com/verygoodplugins/robinhood-mcp/commit/d0849f32f18d746d3ee9d19f71759fdaaac819dd))

## [0.1.2](https://github.com/verygoodplugins/robinhood-mcp/compare/v0.1.1...v0.1.2) (2026-03-08)


### Bug Fixes

* add cached single-symbol position lookup ([c450137](https://github.com/verygoodplugins/robinhood-mcp/commit/c450137ae8262647bc230aff23cd3006c5132a6b))
* harden push approval auth flow ([#6](https://github.com/verygoodplugins/robinhood-mcp/issues/6)) ([b780493](https://github.com/verygoodplugins/robinhood-mcp/commit/b78049390d391ad175406ebad14424f47720890e))

## [0.1.1](https://github.com/verygoodplugins/robinhood-mcp/compare/v0.1.0...v0.1.1) (2026-03-05)


### Bug Fixes

* correct type annotation for _safe_call func parameter ([#3](https://github.com/verygoodplugins/robinhood-mcp/issues/3)) ([6966500](https://github.com/verygoodplugins/robinhood-mcp/commit/696650080d6bb05c8aff30bc8bc4cc9f0bd4e4c2))

## [0.1.0] - 2026-01-06

### Added
- Initial release with 12 read-only tools
- Portfolio and positions tracking
- Stock quotes, fundamentals, and historicals
- News, earnings, and analyst ratings
- Dividend history
- Options positions (read-only)
- Symbol search
- TOTP-based 2FA support

[0.1.0]: https://github.com/verygoodplugins/robinhood-mcp/releases/tag/v0.1.0
