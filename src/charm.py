#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Charm for Beszel Hub - lightweight server monitoring platform."""

from __future__ import annotations

import dataclasses
import logging

import ops
import pydantic
from charms.data_platform_libs.v0 import s3
from charms.hydra.v0 import oauth
from charms.traefik_k8s.v2 import ingress

import beszel

logger = logging.getLogger(__name__)

CONTAINER_NAME = "beszel"
SERVICE_NAME = "beszel"
CHECK_NAME = "beszel-ready"
DEFAULT_PORT = 8090


class BeszelConfig(pydantic.BaseModel):
    """Configuration for Beszel Hub.

    Attrs:
        container_image: OCI image to use for Beszel Hub.
        port: Port on which Beszel Hub listens.
        external_hostname: External hostname for OAuth callbacks.
        s3_backup_enabled: Enable S3 backups.
        s3_endpoint: S3 endpoint URL.
        s3_bucket: S3 bucket name.
        s3_region: S3 region.
        log_level: Log verbosity level.
    """

    container_image: str = "henrygd/beszel:latest"
    port: int = pydantic.Field(default=DEFAULT_PORT, ge=1, le=65535)
    external_hostname: str = ""
    s3_backup_enabled: bool = False
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    log_level: str = "info"


@dataclasses.dataclass(frozen=True, kw_only=True)
class CreateAgentTokenParams:
    """Parameters for the create-agent-token action.

    Attrs:
        description: Description to associate with the generated token.
    """

    description: str = ""


class BeszelCharm(ops.CharmBase):
    """Charm for Beszel Hub."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        self.container = self.unit.get_container(CONTAINER_NAME)

        # Relations. The ingress port is read directly from config (rather than
        # via load_config) so that invalid config cannot raise during __init__.
        self.ingress = ingress.IngressPerAppRequirer(
            self, port=int(self.config.get("port", DEFAULT_PORT)), strip_prefix=True
        )
        self.oauth = oauth.OAuthRequirer(self, client_config=self._get_oauth_client_config())
        self.s3 = s3.S3Requirer(self, "s3-credentials")

        framework.observe(self.on[CONTAINER_NAME].pebble_ready, self._on_pebble_ready)
        framework.observe(
            self.on[CONTAINER_NAME].pebble_check_failed, self._on_pebble_check_failed
        )
        framework.observe(self.on.config_changed, self._on_config_changed)
        framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        framework.observe(self.on.collect_unit_status, self._on_collect_status)

        framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        framework.observe(self.oauth.on.oauth_info_changed, self._on_oauth_info_changed)

        framework.observe(self.s3.on.credentials_changed, self._on_s3_credentials_changed)
        framework.observe(self.s3.on.credentials_gone, self._on_s3_credentials_gone)

        framework.observe(self.on.get_admin_url_action, self._on_get_admin_url_action)
        framework.observe(self.on.create_agent_token_action, self._on_create_agent_token_action)
        framework.observe(self.on.backup_now_action, self._on_backup_now_action)
        framework.observe(self.on.list_backups_action, self._on_list_backups_action)

    def _get_oauth_client_config(self) -> oauth.ClientConfig | None:
        """Get OAuth client configuration.

        Returns:
            OAuth client configuration if an external hostname is set, None otherwise.
        """
        external_hostname = str(self.config.get("external-hostname") or "")
        if not external_hostname:
            return None
        return oauth.ClientConfig(
            redirect_uri=f"https://{external_hostname}/_/#/auth/oidc",
            scope="openid profile email",
            grant_types=["authorization_code"],
        )

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        self._configure_workload()

    def _on_pebble_check_failed(self, event: ops.PebbleCheckFailedEvent) -> None:
        # The on-check-failure action in the Pebble layer restarts the service;
        # we just record that the check tripped.
        logger.warning("Pebble check '%s' failed", event.info.name)

    def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
        self._configure_workload()

    def _on_upgrade_charm(self, event: ops.UpgradeCharmEvent) -> None:
        self._configure_workload()

    def _on_ingress_ready(self, event: ingress.IngressPerAppReadyEvent) -> None:
        logger.info("Ingress is ready at %s", event.url)
        self._configure_workload()

    def _on_ingress_revoked(self, event: ingress.IngressPerAppRevokedEvent) -> None:
        logger.info("Ingress has been revoked")
        self._configure_workload()

    def _on_oauth_info_changed(self, event: oauth.OAuthInfoChangedEvent) -> None:
        logger.info("OAuth information has changed")
        self._configure_workload()

    def _on_s3_credentials_changed(self, event: s3.CredentialsChangedEvent) -> None:
        logger.info("S3 credentials have changed")
        self._configure_workload()

    def _on_s3_credentials_gone(self, event: s3.CredentialsGoneEvent) -> None:
        logger.info("S3 credentials have been removed")
        self._configure_workload()

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
        """Report the unit status based on the current state of the workload."""
        try:
            self.load_config(BeszelConfig)
        except ValueError as e:
            event.add_status(ops.BlockedStatus(f"Invalid configuration: {e}"))

        if not self._storage_attached():
            event.add_status(ops.BlockedStatus("Storage not attached"))

        if not self.container.can_connect():
            event.add_status(ops.WaitingStatus("Waiting for Pebble"))
        else:
            try:
                service_running = self.container.get_service(SERVICE_NAME).is_running()
            except (ops.ModelError, ops.pebble.ConnectionError):
                service_running = False
            if not service_running:
                event.add_status(ops.MaintenanceStatus("Waiting for the service to start"))

        event.add_status(ops.ActiveStatus())

    def _storage_attached(self) -> bool:
        """Report whether the beszel-data storage is attached."""
        try:
            return bool(list(self.model.storages["beszel-data"]))
        except (KeyError, ops.ModelError):
            return False

    def _configure_workload(self) -> None:
        """Configure the Beszel workload.

        Status is reported separately via the collect-status handler.
        """
        if not self.container.can_connect() or not self._storage_attached():
            return

        try:
            config = self.load_config(BeszelConfig)
        except ValueError:
            # The collect-status handler reports the configuration error.
            return

        # Keep the published ingress port in sync with the configured port.
        self.ingress.provide_ingress_requirements(port=config.port)

        env = self._build_environment(config)
        layer = self._build_pebble_layer(config, env)
        self.container.add_layer(SERVICE_NAME, layer, combine=True)
        self.container.replan()

        version = beszel.get_version(self.container)
        if version:
            self.unit.set_workload_version(version)

    def _build_environment(self, config: BeszelConfig) -> dict[str, str]:
        """Build environment variables for Beszel.

        Args:
            config: Beszel configuration.

        Returns:
            Environment variables dictionary.
        """
        env = {
            "PORT": str(config.port),
            "LOG_LEVEL": config.log_level.upper(),
        }

        if self.oauth.is_client_created():
            provider_info = self.oauth.get_provider_info()
            if provider_info and provider_info.client_id and provider_info.client_secret:
                env["OIDC_CLIENT_ID"] = provider_info.client_id
                env["OIDC_CLIENT_SECRET"] = provider_info.client_secret
                env["OIDC_ISSUER_URL"] = provider_info.issuer_url
                env["OIDC_REDIRECT_URI"] = f"https://{config.external_hostname}/_/#/auth/oidc"

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
        """Build the Pebble layer for Beszel.

        Args:
            config: Beszel configuration.
            env: Environment variables.

        Returns:
            Pebble layer dictionary.
        """
        return {
            "summary": "Beszel Hub service",
            "services": {
                SERVICE_NAME: {
                    "override": "replace",
                    "summary": "Beszel Hub server monitoring service",
                    "command": "/beszel serve",
                    "startup": "enabled",
                    "environment": env,
                    "on-check-failure": {CHECK_NAME: "restart"},
                }
            },
            "checks": {
                CHECK_NAME: {
                    "override": "replace",
                    "level": "ready",
                    "http": {"url": f"http://localhost:{config.port}/"},
                    "period": "10s",
                    "threshold": 3,
                }
            },
        }

    def _admin_url(self, config: BeszelConfig) -> str:
        """Return the best-known URL for reaching the Beszel Hub."""
        if self.ingress.url:
            return self.ingress.url
        if config.external_hostname:
            return f"https://{config.external_hostname}"
        return f"http://{self.app.name}:{config.port}"

    def _on_get_admin_url_action(self, event: ops.ActionEvent) -> None:
        config = self.load_config(BeszelConfig)
        event.set_results({"url": self._admin_url(config)})

    def _on_create_agent_token_action(self, event: ops.ActionEvent) -> None:
        params = event.load_params(CreateAgentTokenParams, errors="fail")

        if not self.container.can_connect():
            event.fail("Container not ready")
            return

        token = beszel.create_agent_token(self.container, params.description)
        if not token:
            event.fail("Failed to create agent token")
            return

        config = self.load_config(BeszelConfig)
        instructions = (
            "Use this token when configuring Beszel agents:\n\n"
            "1. Install the Beszel agent on the system to monitor\n"
            "2. Configure the agent with:\n"
            f"   HUB_URL={self._admin_url(config)}\n"
            f"   TOKEN={token}\n"
            "3. Start the agent service\n\n"
            "See https://beszel.dev/guide/getting-started for more details."
        )
        event.set_results({"token": token, "instructions": instructions})

    def _on_backup_now_action(self, event: ops.ActionEvent) -> None:
        if not self.container.can_connect():
            event.fail("Container not ready")
            return

        backup_info = beszel.create_backup(self.container)
        if not backup_info:
            event.fail("Failed to create backup")
            return

        event.set_results(backup_info)

    def _on_list_backups_action(self, event: ops.ActionEvent) -> None:
        if not self.container.can_connect():
            event.fail("Container not ready")
            return

        event.set_results({"backups": beszel.list_backups(self.container)})


if __name__ == "__main__":  # pragma: nocover
    ops.main(BeszelCharm)
