#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Charm for Beszel Hub - lightweight server monitoring platform."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import ops
from charms.data_platform_libs.v0 import s3
from charms.hydra.v0 import oauth
from charms.traefik_k8s.v2 import ingress
from pydantic import BaseModel, Field

import beszel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CONTAINER_NAME = "beszel"
SERVICE_NAME = "beszel"
BESZEL_DATA_DIR = "/beszel_data"


class BeszelConfig(BaseModel):
    """Configuration for Beszel Hub.

    Attrs:
        container_image: OCI image to use for Beszel Hub
        port: Port on which Beszel Hub listens
        external_hostname: External hostname for OAuth callbacks
        s3_backup_enabled: Enable S3 backups
        s3_endpoint: S3 endpoint URL
        s3_bucket: S3 bucket name
        s3_region: S3 region
        log_level: Log verbosity level
    """

    container_image: str = Field(default="henrygd/beszel:latest")
    port: int = Field(default=8090, ge=1, le=65535)
    external_hostname: str = Field(default="")
    s3_backup_enabled: bool = Field(default=False)
    s3_endpoint: str = Field(default="")
    s3_bucket: str = Field(default="")
    s3_region: str = Field(default="us-east-1")
    log_level: str = Field(default="info")

    @classmethod
    def from_charm_config(cls, config: ops.ConfigData) -> BeszelConfig:
        """Create configuration from charm config.

        Args:
            config: Charm configuration

        Returns:
            BeszelConfig instance
        """
        return cls(
            container_image=str(config.get("container-image", "henrygd/beszel:latest")),
            port=int(config.get("port", 8090)),
            external_hostname=str(config.get("external-hostname", "")),
            s3_backup_enabled=bool(config.get("s3-backup-enabled", False)),
            s3_endpoint=str(config.get("s3-endpoint", "")),
            s3_bucket=str(config.get("s3-bucket", "")),
            s3_region=str(config.get("s3-region", "us-east-1")),
            log_level=str(config.get("log-level", "info")),
        )


class BeszelCharm(ops.CharmBase):
    """Charm for Beszel Hub."""

    def __init__(self, framework: ops.Framework):
        """Initialize the charm.

        Args:
            framework: Ops framework
        """
        super().__init__(framework)

        self.container = self.unit.get_container(CONTAINER_NAME)

        # Relations
        self.ingress = ingress.IngressPerAppRequirer(self, port=8090, strip_prefix=True)
        self.oauth = oauth.OAuthRequirer(self, client_config=self._get_oauth_client_config())
        self.s3 = s3.S3Requirer(self, "s3-credentials")

        # Event handlers
        framework.observe(self.on[CONTAINER_NAME].pebble_ready, self._on_pebble_ready)
        framework.observe(
            self.on[CONTAINER_NAME].pebble_check_failed, self._on_pebble_check_failed
        )
        framework.observe(self.on.config_changed, self._on_config_changed)
        framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

        # Ingress relation events
        framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        # OAuth relation events
        framework.observe(self.oauth.on.oauth_info_changed, self._on_oauth_info_changed)

        # S3 relation events
        framework.observe(self.s3.on.credentials_changed, self._on_s3_credentials_changed)
        framework.observe(self.s3.on.credentials_gone, self._on_s3_credentials_gone)

        # Actions
        framework.observe(self.on.get_admin_url_action, self._on_get_admin_url_action)
        framework.observe(self.on.create_agent_token_action, self._on_create_agent_token_action)
        framework.observe(self.on.backup_now_action, self._on_backup_now_action)
        framework.observe(self.on.list_backups_action, self._on_list_backups_action)

    def _get_oauth_client_config(self) -> oauth.ClientConfig | None:
        """Get OAuth client configuration.

        Returns:
            OAuth client configuration if external hostname is set, None otherwise
        """
        config = BeszelConfig.from_charm_config(self.config)

        if not config.external_hostname:
            return None

        redirect_uri = f"https://{config.external_hostname}/_/#/auth/oidc"

        return oauth.ClientConfig(
            redirect_uri=redirect_uri,
            scope="openid profile email",
            grant_types=["authorization_code"],
        )

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        """Handle pebble-ready event.

        Args:
            event: Pebble ready event
        """
        self._configure_workload()

    def _on_pebble_check_failed(self, event: ops.PebbleCheckFailedEvent) -> None:
        """Handle pebble check failed event.

        Args:
            event: Pebble check failed event
        """
        logger.warning("Pebble check '%s' failed", event.info.name)
        # The on-check-failure action in the Pebble layer will restart the service
        # We just log the event and let Pebble handle the recovery

    def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
        """Handle config-changed event.

        Args:
            event: Config changed event
        """
        self._configure_workload()

    def _on_upgrade_charm(self, event: ops.UpgradeCharmEvent) -> None:
        """Handle upgrade-charm event.

        Args:
            event: Upgrade charm event
        """
        self._configure_workload()

    def _on_ingress_ready(self, event: ingress.IngressPerAppReadyEvent) -> None:
        """Handle ingress ready event.

        Args:
            event: Ingress ready event
        """
        logger.info("Ingress is ready at %s", event.url)
        self._configure_workload()

    def _on_ingress_revoked(self, event: ingress.IngressPerAppRevokedEvent) -> None:
        """Handle ingress revoked event.

        Args:
            event: Ingress revoked event
        """
        logger.info("Ingress has been revoked")
        self._configure_workload()

    def _on_oauth_info_changed(self, event: oauth.OAuthInfoChangedEvent) -> None:
        """Handle OAuth info changed event.

        Args:
            event: OAuth info changed event
        """
        logger.info("OAuth information has changed")
        self._configure_workload()

    def _on_s3_credentials_changed(self, event: s3.CredentialsChangedEvent) -> None:
        """Handle S3 credentials changed event.

        Args:
            event: S3 credentials changed event
        """
        logger.info("S3 credentials have changed")
        self._configure_workload()

    def _on_s3_credentials_gone(self, event: s3.CredentialsGoneEvent) -> None:
        """Handle S3 credentials gone event.

        Args:
            event: S3 credentials gone event
        """
        logger.info("S3 credentials have been removed")
        self._configure_workload()

    def _configure_workload(self) -> None:
        """Configure the Beszel workload."""
        if not self.container.can_connect():
            self.unit.status = ops.WaitingStatus("Waiting for Pebble")
            return

        config = BeszelConfig.from_charm_config(self.config)

        # Check for required storage
        try:
            if not list(self.model.storages["beszel-data"]):
                self.unit.status = ops.BlockedStatus("Storage not attached")
                return
        except (KeyError, ops.ModelError):
            self.unit.status = ops.BlockedStatus("Storage not attached")
            return

        # Build environment variables
        env = self._build_environment(config)

        # Create Pebble layer
        layer = self._build_pebble_layer(config, env)

        # Add layer to container
        self.container.add_layer(SERVICE_NAME, layer, combine=True)

        # Restart service if configuration changed
        self.container.replan()

        # Wait for service to be ready
        if not beszel.wait_for_ready(self.container):
            self.unit.status = ops.MaintenanceStatus("Waiting for service to start")
            return

        # Set workload version
        version = beszel.get_version(self.container)
        if version:
            self.unit.set_workload_version(version)

        self.unit.status = ops.ActiveStatus()

    def _build_environment(self, config: BeszelConfig) -> dict[str, str]:
        """Build environment variables for Beszel.

        Args:
            config: Beszel configuration

        Returns:
            Environment variables dictionary
        """
        env = {
            "PORT": str(config.port),
            "LOG_LEVEL": config.log_level.upper(),
        }

        # Add OAuth configuration if available
        if self.oauth.is_client_created():
            provider_info = self.oauth.get_provider_info()
            if provider_info and provider_info.client_id and provider_info.client_secret:
                env["OIDC_CLIENT_ID"] = provider_info.client_id
                env["OIDC_CLIENT_SECRET"] = provider_info.client_secret
                env["OIDC_ISSUER_URL"] = provider_info.issuer_url
                env["OIDC_REDIRECT_URI"] = f"https://{config.external_hostname}/_/#/auth/oidc"

        # Add S3 configuration if enabled and available
        if config.s3_backup_enabled:
            s3_params = self.s3.get_s3_connection_info()
            if s3_params:
                env["S3_BACKUP_ENABLED"] = "true"
                env["S3_ENDPOINT"] = s3_params.get("endpoint", config.s3_endpoint)
                env["S3_BUCKET"] = s3_params.get("bucket", config.s3_bucket)
                env["S3_REGION"] = s3_params.get("region", config.s3_region)
                env["S3_ACCESS_KEY_ID"] = s3_params.get("access-key", "")
                env["S3_SECRET_ACCESS_KEY"] = s3_params.get("secret-key", "")

        return env

    def _build_pebble_layer(
        self, config: BeszelConfig, env: dict[str, str]
    ) -> ops.pebble.LayerDict:
        """Build Pebble layer for Beszel.

        Args:
            config: Beszel configuration
            env: Environment variables

        Returns:
            Pebble layer dictionary
        """
        layer: ops.pebble.LayerDict = {
            "summary": "Beszel Hub service",
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "summary": "Beszel Hub server monitoring service",
                    "command": "/beszel serve",
                    "startup": "enabled",
                    "environment": env,
                    "on-check-failure": {"beszel-ready": "restart"},
                }
            },
            "checks": {
                "beszel-ready": {
                    "override": "replace",
                    "level": "ready",
                    "http": {"url": f"http://localhost:{config.port}/"},
                    "period": "10s",
                    "threshold": 3,
                }
            },
        }

        return layer

    def _on_get_admin_url_action(self, event: ops.ActionEvent) -> None:
        """Handle get-admin-url action.

        Args:
            event: Action event
        """
        config = BeszelConfig.from_charm_config(self.config)

        # Try to get URL from ingress first
        if self.ingress.url:
            url = self.ingress.url
        elif config.external_hostname:
            url = f"https://{config.external_hostname}"
        else:
            url = f"http://{self.app.name}:{config.port}"

        event.set_results({"url": url})

    def _on_create_agent_token_action(self, event: ops.ActionEvent) -> None:
        """Handle create-agent-token action.

        Args:
            event: Action event
        """
        description = event.params.get("description", "")

        if not self.container.can_connect():
            event.fail("Container not ready")
            return

        token = beszel.create_agent_token(self.container, description)

        if not token:
            event.fail("Failed to create agent token")
            return

        instructions = (
            "Use this token when configuring Beszel agents:\n\n"
            "1. Install the Beszel agent on the system to monitor\n"
            "2. Configure the agent with:\n"
            f"   HUB_URL={self.ingress.url or f'http://{self.app.name}:8090'}\n"
            f"   TOKEN={token}\n"
            "3. Start the agent service\n\n"
            "See https://beszel.dev/guide/getting-started for more details."
        )

        event.set_results({"token": token, "instructions": instructions})

    def _on_backup_now_action(self, event: ops.ActionEvent) -> None:
        """Handle backup-now action.

        Args:
            event: Action event
        """
        if not self.container.can_connect():
            event.fail("Container not ready")
            return

        backup_info = beszel.create_backup(self.container)

        if not backup_info:
            event.fail("Failed to create backup")
            return

        event.set_results(backup_info)

    def _on_list_backups_action(self, event: ops.ActionEvent) -> None:
        """Handle list-backups action.

        Args:
            event: Action event
        """
        if not self.container.can_connect():
            event.fail("Container not ready")
            return

        backups = beszel.list_backups(self.container)

        event.set_results({"backups": backups})


if __name__ == "__main__":  # pragma: nocover
    ops.main(BeszelCharm)
