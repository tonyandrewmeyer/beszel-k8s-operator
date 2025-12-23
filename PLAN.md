# Beszel Kubernetes Charm - Implementation Plan

## Overview

Beszel is a lightweight server monitoring platform that provides Docker/Podman statistics, historical data, and alerts. This charm will deploy the **Beszel Hub** component as a Kubernetes workload.

### Architecture

Beszel has two main components:
- **Hub**: A web application built on PocketBase that serves as the central dashboard for viewing and managing monitored systems
- **Agent**: Lightweight monitoring service that runs on each system to be monitored (not part of this charm)

This charm focuses on deploying and managing the Hub component in Kubernetes.

## Charm Type: Kubernetes

**Rationale:**
- Beszel Hub is distributed as an OCI image (`henrygd/beszel`)
- It's a stateful web application well-suited for container deployment
- Scales horizontally (though typically deployed as a single instance due to PocketBase backend)
- Repository name suggests Kubernetes deployment intent

## Configuration Options

The charm will expose the following configuration options via `config` in `charmcraft.yaml`:

### Core Configuration

1. **`container-image`** (string, default: `"henrygd/beszel:latest"`)
   - OCI image to use for the Beszel Hub
   - Allows users to pin specific versions or use custom builds

2. **`port`** (int, default: `8090`)
   - Port on which the Beszel Hub listens
   - Matches Beszel's default port

### Authentication & Security

3. **`external-hostname`** (string, default: `""`)
   - External hostname for OAuth callback URLs (e.g., "beszel.example.com")
   - Required when using oauth relation with identity platform
   - If not set, falls back to local authentication only

### Backup Configuration

4. **`s3-backup-enabled`** (bool, default: `false`)
   - Enable automatic backups to S3-compatible storage

5. **`s3-endpoint`** (string, default: `""`)
   - S3-compatible storage endpoint URL
   - Required if s3-backup-enabled is true

6. **`s3-bucket`** (string, default: `""`)
   - S3 bucket name for backups

7. **`s3-region`** (string, default: `"us-east-1"`)
   - S3 region

### Operational

8. **`log-level`** (string, default: `"info"`)
   - Log verbosity level (debug, info, warn, error)

## Actions

The charm will provide the following actions:

### 1. `get-admin-url`
- Returns the URL to access the Beszel Hub admin interface
- Output: `url` (string)
- No parameters required

### 2. `create-agent-token`
- Creates a universal token for agent authentication
- Output: `token` (string), `instructions` (string with setup guidance)
- Parameters:
  - `description` (string, optional): Description for the token

### 3. `backup-now`
- Triggers an immediate backup
- Output: `backup-path` (string), `timestamp` (string)
- No parameters required

### 4. `list-backups`
- Lists available backups
- Output: `backups` (JSON array)
- No parameters required

## Storage

### Database Storage (`beszel-data`)
- **Type**: filesystem
- **Mount point**: `/beszel_data` (inside container)
- **Purpose**: Stores PocketBase database, configuration, and local backups
- **Minimum size**: 1GB (configurable by user during deployment)
- **Required**: Yes

## Resources

### OCI Image (`beszel-image`)
- **Type**: oci-image
- **Description**: The Beszel Hub OCI image
- **Upstream source**: `henrygd/beszel:latest`

This resource will be defined but the default image will be pulled from Docker Hub. Users can optionally provide their own image via Juju resources.

## Relations (Integrations)

The charm will support the following relations:

### 1. Ingress (`ingress`)
- **Interface**: `ingress`
- **Role**: requires
- **Purpose**: Expose Beszel Hub via Kubernetes Ingress
- **Related charms**: nginx-ingress-integrator, traefik-k8s
- **Optional**: Yes (can be accessed via LoadBalancer or NodePort without ingress)

### 2. S3 Credentials (`s3-credentials`)
- **Interface**: `s3`
- **Role**: requires
- **Purpose**: Obtain S3 credentials for automatic backups
- **Related charms**: s3-integrator, minio
- **Optional**: Yes (S3 backups are optional)

### 3. OAuth / OIDC (`oauth`)
- **Interface**: `oauth`
- **Role**: requires
- **Purpose**: Integrate with Identity Platform (Hydra) for OAuth/OIDC authentication
- **Related charms**: identity-platform (specifically hydra)
- **Optional**: Yes (can use built-in password authentication if not provided)
- **Library**: `charms.hydra.v0.oauth`
- **Configuration**: Requires `external-hostname` to be set for proper callback URL configuration

## Secrets

The following secrets will be managed via Juju secrets or relations:

1. **S3 Credentials** (if S3 integration is used)
   - Access key and secret key
   - Obtained from s3-credentials relation

2. **OAuth Client Credentials** (from oauth relation)
   - Client ID and client secret
   - Obtained automatically from oauth relation with identity-platform/hydra
   - Used to configure Beszel for OIDC authentication

## Scaling Considerations

- **Single Instance**: Initially, the charm will support single-unit deployment only
  - Beszel Hub uses PocketBase with SQLite, which is single-instance
  - Peer relation not required for initial implementation

- **Future Multi-Instance**:
  - Would require external PostgreSQL support in Beszel
  - Session affinity via ingress
  - Shared storage or database for multi-unit consistency

## Workload Container

### Pebble Configuration

The charm will configure Pebble to manage the Beszel Hub service:

```yaml
services:
  beszel:
    override: replace
    summary: Beszel Hub server monitoring service
    command: /beszel serve
    startup: enabled
    environment:
      PORT: "8090"
      # Additional environment variables based on config
```

### Health Checks

- **Startup probe**: HTTP GET `http://localhost:8090/api/health`
- **Liveness probe**: HTTP GET `http://localhost:8090/api/health`
- **Readiness probe**: HTTP GET `http://localhost:8090/api/health`

(Note: Actual health endpoint needs to be confirmed from Beszel documentation)

## Container Port

The workload container will expose port 8090 (configurable) for the web interface and API.

## Status Messages

The charm will provide clear status messages:

- **Maintenance**: "Configuring Beszel Hub", "Starting service"
- **Active**: "Beszel Hub is ready" (when service is running and healthy)
- **Blocked**: "Waiting for storage", "S3 configuration incomplete" (when S3 enabled but credentials missing)
- **Waiting**: "Waiting for ingress relation" (optional, informational)

## Event Handling

The charm will observe and handle:

1. **config-changed**: Update Pebble configuration, restart service if needed
2. **beszel-pebble-ready**: Initial service configuration and startup
3. **upgrade-charm**: Handle charm upgrades, update Pebble config
4. **ingress-relation-joined/changed**: Configure ingress for external access
5. **s3-credentials-relation-joined/changed**: Configure S3 backup settings
6. **storage-attached**: Ensure storage is properly mounted

## Implementation Phases

### Phase 1: Basic Deployment (MVP)
- [ ] Basic charm structure with configuration dataclass
- [ ] Pebble layer configuration for Beszel Hub service
- [ ] Storage integration for /beszel_data
- [ ] Basic health checking
- [ ] `get-admin-url` action

### Phase 2: Ingress & Networking
- [ ] Ingress relation implementation
- [ ] Proper external URL handling
- [ ] TLS/HTTPS configuration via ingress

### Phase 3: Identity Platform Integration
- [ ] OAuth relation implementation using `charms.hydra.v0.oauth` library
- [ ] Configure Beszel with OIDC client credentials
- [ ] Handle external hostname configuration for callbacks
- [ ] Testing with identity-platform bundle

### Phase 4: S3 Backups & Additional Features
- [ ] S3 credentials relation
- [ ] S3 backup configuration
- [ ] `backup-now` and `list-backups` actions
- [ ] `create-agent-token` action

## Testing Strategy

Following the "testing sandwich" approach:

### Integration Tests (First)
1. Deploy charm with storage
2. Verify service is running and accessible
3. Test ingress relation integration
4. Test S3 backup configuration
5. Test actions (get-admin-url, backup-now, etc.)
6. Test configuration changes and service restart
7. Test upgrade scenarios

### Unit Tests (After Implementation)
1. Test Pebble layer generation with various configs
2. Test event handlers with different state transitions
3. Test relation data handling
4. Test error conditions and status messages

### Manual Testing
1. Access web UI and create admin user
2. Add monitoring systems and verify functionality
3. Test backups and restores

## Dependencies

### Python Dependencies (in pyproject.toml)
- ops >= 2.0
- httpx (for health checks and API interaction)
- pydantic (for configuration validation)

### Charm Libraries
- ingress library (for ingress relation)
- s3 library (for S3 integration)

These will be added to `charmcraft.yaml` and fetched via `charmcraft fetch-libs`.

## Security Considerations

1. **Secrets Management**: Use Juju secrets for sensitive data (OAuth secrets, S3 credentials)
2. **Network Policies**: Restrict ingress to necessary ports only
3. **User Data**: Ensure PocketBase data directory has appropriate permissions
4. **Input Validation**: Validate all configuration inputs
5. **Default Passwords**: Require users to set admin password on first access (Beszel handles this)

## Documentation Deliverables

1. **README.md**: Overview, deployment instructions, configuration reference
2. **CONTRIBUTING.md**: Development setup, testing, contribution guidelines (already scaffolded)
3. **TUTORIAL.md**: Step-by-step guide to deploy and use the charm
4. **SECURITY.md**: Security reporting process
5. **CODE_OF_CONDUCT.md**: Contributor Covenant
6. **CHANGELOG.md**: Track all changes with conventional commit types

## Open Questions

1. **Health endpoint**: Does Beszel expose a dedicated health check endpoint? Need to verify actual API paths.
2. **Environment variables**: What environment variables does Beszel Hub support? Need to review Beszel documentation/source.
3. **OIDC configuration in Beszel**: How does Beszel/PocketBase configure OIDC providers? File-based, environment variables, or API configuration?
4. **Multi-tenancy**: How does Beszel handle multiple users in a single instance? Any special configuration needed?
5. **Backup restore**: Is there a restore mechanism needed? Should we provide a restore action?

## References

- [Identity Platform on Charmhub](https://charmhub.io/topics/canonical-identity-platform)
- [Hydra OAuth Integration Guide](https://charmhub.io/hydra/docs/how-to/integrate-oidc-compatible-charms)
- [OAuth Charm Library Source Code](https://charmhub.io/hydra/libraries/oauth/source-code)
- [Beszel Documentation](https://www.beszel.dev/)

## Next Steps

1. Get user approval for this plan
2. Update CLAUDE.md with Beszel-specific details
3. Start implementing integration tests (testing sandwich approach)
4. Implement the charm following the phases above
5. Validate with integration tests
6. Add unit tests
7. Complete documentation
