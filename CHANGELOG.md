# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial implementation of Beszel Hub charm for Kubernetes
- Pebble layer configuration with health checks for Beszel service using `/beszel health` command
- Storage integration for PocketBase database (`/beszel_data`)
- Ingress integration via `traefik-k8s` for external access (tested with nginx-ingress-integrator)
- OAuth/OIDC integration via `hydra` for authentication with identity-platform
- S3 backup integration via `data-platform-libs` for automated backups
- Configuration options for port, external hostname, S3 backups, and log level
- Actions:
  - `get-admin-url`: Retrieve the URL to access Beszel Hub admin interface (supports ingress URL detection)
  - `create-agent-token`: Generate authentication tokens for Beszel agents
  - `backup-now`: Trigger immediate database backup using Pebble pull/push APIs
  - `list-backups`: List all available backups using Pebble list_files API
- 17 comprehensive unit tests using ops.testing.Context
- 15 integration test scenarios covering deployment, relations, actions, and upgrades
- Workload interaction module (`beszel.py`) for version checks, health monitoring, and backup management
- Complete documentation: README, TUTORIAL, SECURITY, CHANGELOG, CONTRIBUTING
- CI/CD workflows: GitHub Actions, Zizmor security scanning, Dependabot, pre-commit hooks

### Changed

- N/A (initial release)

### Deprecated

- N/A

### Removed

- N/A

### Fixed

- Workload version detection to use `/beszel --version` and parse "beszel version X.Y.Z" format correctly
- Health check configuration to use Beszel's native `/beszel health` command with 60s period
- Backup implementation to use Pebble pull/push APIs instead of shell exec commands
- List backups implementation to use Pebble list_files API instead of shell exec commands
- All dependencies properly included in uv.lock (jsonschema, pydantic, httpx, etc.)

### Security

- OAuth client credentials managed securely via Juju secrets
- S3 credentials obtained from relation data
- No hardcoded secrets in charm code
- All shell commands eliminated from backup operations

[Unreleased]: https://github.com/your-org/beszel-operator/compare/v0.0.0...HEAD
