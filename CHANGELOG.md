# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial implementation of Beszel Hub charm for Kubernetes
- Pebble layer configuration with health checks for Beszel service
- Storage integration for PocketBase database (`/beszel_data`)
- Ingress integration via `traefik-k8s` for external access
- OAuth/OIDC integration via `hydra` for authentication with identity-platform
- S3 backup integration via `data-platform-libs` for automated backups
- Configuration options for port, external hostname, S3 backups, and log level
- Actions:
  - `get-admin-url`: Retrieve the URL to access Beszel Hub admin interface
  - `create-agent-token`: Generate authentication tokens for Beszel agents
  - `backup-now`: Trigger immediate database backup
  - `list-backups`: List all available backups
- Comprehensive integration tests covering deployment, relations, actions, and upgrades
- Workload interaction module (`beszel.py`) for version checks, health monitoring, and backup management

### Changed

- N/A (initial release)

### Deprecated

- N/A

### Removed

- N/A

### Fixed

- N/A

### Security

- OAuth client credentials managed securely via Juju secrets
- S3 credentials obtained from relation data
- No hardcoded secrets in charm code

[Unreleased]: https://github.com/your-org/beszel-operator/compare/v0.0.0...HEAD
