# Beszel Hub Operator

A Juju charm for deploying and managing [Beszel Hub](https://beszel.dev), a lightweight server monitoring platform with Docker stats, historical data, and alerts.

## Overview

Beszel is a lightweight server monitoring solution that tracks system metrics, Docker/Podman container statistics, and provides customizable alerts. This charm deploys the **Beszel Hub** component, which serves as the central dashboard for viewing and managing monitored systems.

### Features

- 🚀 **Easy deployment** on Kubernetes via Juju
- 📊 **Persistent storage** for PocketBase database
- 🔐 **OAuth/OIDC authentication** via identity-platform integration
- 🌐 **Ingress support** for external access
- 💾 **S3-compatible backups** for data protection
- 🔧 **Actions** for URL retrieval, token generation, and backup management
- 📈 **Health monitoring** with automated service restarts

## Requirements

- Juju >= 3.1
- Kubernetes cluster
- Storage provider (for persistent volume)

## Quick Start

### Deploy the charm

```bash
juju deploy beszel --channel=edge \
  --storage beszel-data=1G
```

### Access the admin interface

```bash
juju run beszel/0 get-admin-url
```

Visit the URL and create your admin user account.

### Configure a monitoring agent

1. Generate an agent token:

```bash
juju run beszel/0 create-agent-token description="my-server"
```

2. Install the Beszel agent on the system to monitor and configure it with the provided token and hub URL.

See the [Beszel documentation](https://beszel.dev/guide/getting-started) for agent installation details.

## Configuration

### Basic Configuration

```bash
# Change the listening port
juju config beszel port=8091

# Set log level
juju config beszel log-level=debug
```

### External Access with Ingress

```bash
# Deploy nginx-ingress-integrator
juju deploy nginx-ingress-integrator --trust

# Configure hostname
juju config nginx-ingress-integrator service-hostname=beszel.example.com

# Integrate
juju integrate beszel nginx-ingress-integrator
```

### OAuth/OIDC Authentication

To enable SSO with the identity platform:

```bash
# Set external hostname (required for OAuth callbacks)
juju config beszel external-hostname=beszel.example.com

# Deploy and integrate with identity-platform
juju deploy identity-platform --channel=edge --trust
juju integrate beszel:oauth identity-platform:oauth
```

### S3 Backups

```bash
# Deploy S3 integrator
juju deploy s3-integrator
juju config s3-integrator \
  endpoint=https://s3.amazonaws.com \
  bucket=my-beszel-backups \
  region=us-east-1

# Provide credentials
juju run s3-integrator/leader sync-s3-credentials \
  access-key=<key> \
  secret-key=<secret>

# Enable backups and integrate
juju config beszel s3-backup-enabled=true
juju integrate beszel s3-integrator
```

## Actions

### get-admin-url

Retrieve the URL to access the Beszel Hub admin interface.

```bash
juju run beszel/0 get-admin-url
```

### create-agent-token

Generate an authentication token for Beszel agents.

```bash
juju run beszel/0 create-agent-token description="production-server"
```

### backup-now

Trigger an immediate backup of the Beszel database.

```bash
juju run beszel/0 backup-now
```

### list-backups

List all available backups.

```bash
juju run beszel/0 list-backups
```

## Relations

| Relation | Interface | Description | Required |
|----------|-----------|-------------|----------|
| `ingress` | `ingress` | Expose via Kubernetes Ingress (traefik, nginx) | No |
| `oauth` | `oauth` | OIDC authentication with identity-platform | No |
| `s3-credentials` | `s3` | S3-compatible backup storage | No |

## Storage

| Storage | Type | Description | Size |
|---------|------|-------------|------|
| `beszel-data` | filesystem | PocketBase database and backups | 1G+ |

Required storage must be specified during deployment:

```bash
juju deploy beszel --storage beszel-data=10G
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and contribution process.

## Security

To report security vulnerabilities, please see [SECURITY.md](SECURITY.md).

## License

This charm is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

## Links

- **Beszel Documentation**: https://beszel.dev
- **Charm Source**: https://github.com/your-org/beszel-operator
- **Juju Documentation**: https://juju.is/docs
- **File Issues**: https://github.com/your-org/beszel-operator/issues

## Related Charms

- [identity-platform](https://charmhub.io/topics/canonical-identity-platform) - OAuth/OIDC authentication
- [nginx-ingress-integrator](https://charmhub.io/nginx-ingress-integrator) - Kubernetes ingress
- [s3-integrator](https://charmhub.io/s3-integrator) - S3 backup storage
