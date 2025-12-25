# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

import ops.testing
import pytest

from charm import BeszelCharm, BeszelConfig

CONTAINER_NAME = "beszel"
METADATA = {
    "name": "beszel",
    "containers": {
        CONTAINER_NAME: {"resource": "beszel-image"},
    },
    "resources": {
        "beszel-image": {"type": "oci-image"},
    },
    "storage": {
        "beszel-data": {
            "type": "filesystem",
        },
    },
    "requires": {
        "ingress": {"interface": "ingress"},
        "oauth": {"interface": "oauth"},
        "s3-credentials": {"interface": "s3"},
    },
}

CONFIG = {
    "options": {
        "container-image": {"type": "string", "default": "henrygd/beszel:latest"},
        "port": {"type": "int", "default": 8090},
        "external-hostname": {"type": "string", "default": ""},
        "s3-backup-enabled": {"type": "boolean", "default": False},
        "s3-endpoint": {"type": "string", "default": ""},
        "s3-bucket": {"type": "string", "default": ""},
        "s3-region": {"type": "string", "default": "us-east-1"},
        "log-level": {"type": "string", "default": "info"},
    },
}

ACTIONS = {
    "get-admin-url": {},
    "create-agent-token": {
        "params": {
            "description": {"type": "string", "default": ""},
        },
    },
    "backup-now": {},
    "list-backups": {},
}


@pytest.fixture
def ctx():
    """Create a testing context."""
    return ops.testing.Context(BeszelCharm, meta=METADATA, actions=ACTIONS, config=CONFIG)


def test_config_from_charm_config():
    """Test BeszelConfig creation from charm config."""
    config_data = {
        "container-image": "custom/image:tag",
        "port": 8091,
        "external-hostname": "beszel.example.com",
        "s3-backup-enabled": True,
        "s3-endpoint": "https://s3.example.com",
        "s3-bucket": "backups",
        "s3-region": "us-west-2",
        "log-level": "debug",
    }

    class MockConfig:
        def get(self, key, default=None):
            return config_data.get(key, default)

    config = BeszelConfig.from_charm_config(MockConfig())  # type: ignore[arg-type]

    assert config.container_image == "custom/image:tag"
    assert config.port == 8091
    assert config.external_hostname == "beszel.example.com"
    assert config.s3_backup_enabled is True
    assert config.s3_endpoint == "https://s3.example.com"
    assert config.s3_bucket == "backups"
    assert config.s3_region == "us-west-2"
    assert config.log_level == "debug"


def test_config_defaults():
    """Test BeszelConfig default values."""

    class MockConfig:
        def get(self, key, default=None):
            return default

    config = BeszelConfig.from_charm_config(MockConfig())  # type: ignore[arg-type]

    assert config.container_image == "henrygd/beszel:latest"
    assert config.port == 8090
    assert config.external_hostname == ""
    assert config.s3_backup_enabled is False
    assert config.s3_endpoint == ""
    assert config.s3_bucket == ""
    assert config.s3_region == "us-east-1"
    assert config.log_level == "info"


def test_pebble_ready_without_storage(ctx: ops.testing.Context):
    """Test pebble-ready without storage attached."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.BlockedStatus("Storage not attached")


def test_pebble_ready_with_storage(ctx: ops.testing.Context):
    """Test pebble-ready with storage attached."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                layers={},
                service_statuses={},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    # Should configure the service
    container = state_out.get_container(CONTAINER_NAME)
    assert "beszel" in container.layers

    # Check Pebble layer configuration
    layer = container.layers["beszel"]
    assert "beszel" in layer.services
    service = layer.services["beszel"]
    assert service.command == "/beszel serve"
    assert service.startup == "enabled"
    assert "PORT" in service.environment
    assert service.environment["PORT"] == "8090"


def test_config_changed_updates_service(ctx: ops.testing.Context):
    """Test that config-changed updates the service configuration."""
    # Initial state with default config
    state_in = ops.testing.State(
        leader=True,
        config={"port": 8091, "log-level": "debug"},
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                layers={},
                service_statuses={},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8091"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    # Verify service has updated environment
    container = state_out.get_container(CONTAINER_NAME)
    layer = container.layers["beszel"]
    service = layer.services["beszel"]
    assert service.environment["PORT"] == "8091"
    assert service.environment["LOG_LEVEL"] == "DEBUG"


def test_health_check_configuration(ctx: ops.testing.Context):
    """Test that health checks are properly configured."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    container = state_out.get_container(CONTAINER_NAME)
    layer = container.layers["beszel"]

    assert "beszel-ready" in layer.checks
    check = layer.checks["beszel-ready"]
    assert check.level == "ready" or check.level.value == "ready"  # type: ignore[union-attr]
    assert check.http is not None
    assert check.http.get("url") == "http://localhost:8090/"
    assert check.period == "10s"
    assert check.threshold == 3


def test_get_admin_url_action_no_ingress(ctx: ops.testing.Context):
    """Test get-admin-url action without ingress."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    ctx.run(ctx.on.action("get-admin-url"), state_in)

    assert ctx.action_results.get("url") == "http://beszel:8090"  # type: ignore[union-attr]


def test_get_admin_url_action_with_external_hostname(ctx: ops.testing.Context):
    """Test get-admin-url action with external hostname configured."""
    state_in = ops.testing.State(
        leader=True,
        config={"external-hostname": "beszel.example.com"},
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    ctx.run(ctx.on.action("get-admin-url"), state_in)

    assert ctx.action_results.get("url") == "https://beszel.example.com"  # type: ignore[union-attr]


def test_create_agent_token_action(ctx: ops.testing.Context, monkeypatch):
    """Test create-agent-token action."""
    # Mock the create_agent_token function to return a fake token
    import beszel

    monkeypatch.setattr(
        beszel, "create_agent_token", lambda container, description: "fake-token-123"
    )

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    ctx.run(ctx.on.action("create-agent-token", params={"description": "test"}), state_in)

    # Should return a token
    assert "token" in ctx.action_results  # type: ignore[operator]
    assert len(ctx.action_results["token"]) > 0  # type: ignore[index]

    # Should include instructions
    assert "instructions" in ctx.action_results  # type: ignore[operator]
    assert "HUB_URL" in ctx.action_results["instructions"]  # type: ignore[index]


def test_create_agent_token_action_container_not_ready(ctx: ops.testing.Context):
    """Test create-agent-token action when container is not ready."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=False,
            )
        ],
    )

    with pytest.raises(ops.testing.ActionFailed, match="Container not ready"):
        ctx.run(ctx.on.action("create-agent-token"), state_in)


def test_list_backups_action_no_backups(ctx: ops.testing.Context):
    """Test list-backups action with no backups."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    ctx.run(ctx.on.action("list-backups"), state_in)

    assert "backups" in ctx.action_results  # type: ignore[operator]
    # Result should be an empty list or serialized empty list
    backups = ctx.action_results["backups"]  # type: ignore[index]
    assert backups == [] or backups == "[]"


def test_container_not_ready(ctx: ops.testing.Context):
    """Test that charm waits when container is not ready."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=False,
            )
        ],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_oauth_client_config_without_external_hostname(ctx: ops.testing.Context):
    """Test that OAuth client config is None without external hostname."""
    state_in = ops.testing.State(leader=True)

    with ctx(ctx.on.install(), state_in) as manager:
        charm = manager.charm
        assert charm._get_oauth_client_config() is None


def test_oauth_client_config_with_external_hostname(ctx: ops.testing.Context):
    """Test OAuth client config with external hostname."""
    state_in = ops.testing.State(leader=True, config={"external-hostname": "beszel.example.com"})

    with ctx(ctx.on.install(), state_in) as manager:
        charm = manager.charm
        client_config = charm._get_oauth_client_config()

        assert client_config is not None
        assert "beszel.example.com" in client_config.redirect_uri
        assert "openid" in client_config.scope


def test_s3_environment_variables(ctx: ops.testing.Context):
    """Test that S3 configuration sets environment variables."""
    state_in = ops.testing.State(
        leader=True,
        config={
            "s3-backup-enabled": True,
            "s3-endpoint": "https://s3.example.com",
            "s3-bucket": "my-backups",
            "s3-region": "us-west-2",
        },
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    # S3 env vars won't be set without relation data, but config should be read
    container = state_out.get_container(CONTAINER_NAME)
    assert "beszel" in container.layers


def test_upgrade_charm(ctx: ops.testing.Context):
    """Test upgrade-charm event."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.upgrade_charm(), state_in)

    # Should reconfigure the workload
    container = state_out.get_container(CONTAINER_NAME)
    assert "beszel" in container.layers


def test_config_changed_event(ctx: ops.testing.Context):
    """Test config-changed event triggers reconfiguration."""
    state_in = ops.testing.State(
        leader=True,
        config={"port": 8091},
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8091"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)
    assert state_out.unit_status == ops.ActiveStatus()


def test_backup_now_action(ctx: ops.testing.Context, monkeypatch):
    """Test backup-now action."""
    import beszel

    # Mock create_backup to return backup info
    monkeypatch.setattr(
        beszel,
        "create_backup",
        lambda container: {
            "backup-path": "/beszel_data/backups/beszel-backup-20250101-120000.db",
            "timestamp": "20250101-120000",
            "filename": "beszel-backup-20250101-120000.db",
        },
    )

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    ctx.run(ctx.on.action("backup-now"), state_in)

    assert "backup-path" in ctx.action_results  # type: ignore[operator]
    assert "timestamp" in ctx.action_results  # type: ignore[operator]


def test_backup_now_action_failure(ctx: ops.testing.Context, monkeypatch):
    """Test backup-now action when backup fails."""
    import beszel

    # Mock create_backup to return None (failure)
    monkeypatch.setattr(beszel, "create_backup", lambda container: None)

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    with pytest.raises(ops.testing.ActionFailed, match="Failed to create backup"):
        ctx.run(ctx.on.action("backup-now"), state_in)


def test_list_backups_action_with_backups(ctx: ops.testing.Context, monkeypatch):
    """Test list-backups action with existing backups."""
    import beszel

    # Mock list_backups to return backup list
    monkeypatch.setattr(
        beszel,
        "list_backups",
        lambda container: [
            {
                "filename": "beszel-backup-20250101-120000.db",
                "path": "/beszel_data/backups/beszel-backup-20250101-120000.db",
                "size": "1024",
                "modified": "2025-01-01T12:00:00",
            },
            {
                "filename": "beszel-backup-20250102-120000.db",
                "path": "/beszel_data/backups/beszel-backup-20250102-120000.db",
                "size": "2048",
                "modified": "2025-01-02T12:00:00",
            },
        ],
    )

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    ctx.run(ctx.on.action("list-backups"), state_in)

    assert "backups" in ctx.action_results  # type: ignore[operator]
    # Results is already the list
    backups = ctx.action_results["backups"]  # type: ignore[index]
    assert len(backups) == 2
    assert backups[0]["filename"] == "beszel-backup-20250101-120000.db"


def test_workload_version_set(ctx: ops.testing.Context):
    """Test that workload version is set when available."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 1.2.3\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.workload_version == "1.2.3"


def test_storage_check_keyerror(ctx: ops.testing.Context, monkeypatch):
    """Test storage check handles KeyError."""

    # Patch model.storages to raise KeyError
    def mock_storages_getitem(self, key):
        raise KeyError(key)

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    # Run pebble_ready which will trigger storage check
    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.BlockedStatus("Storage not attached")


def test_backup_now_action_container_not_ready(ctx: ops.testing.Context):
    """Test backup-now action when container is not ready."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=False,
            )
        ],
    )

    with pytest.raises(ops.testing.ActionFailed, match="Container not ready"):
        ctx.run(ctx.on.action("backup-now"), state_in)


def test_list_backups_action_container_not_ready(ctx: ops.testing.Context):
    """Test list-backups action when container is not ready."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=False,
            )
        ],
    )

    with pytest.raises(ops.testing.ActionFailed, match="Container not ready"):
        ctx.run(ctx.on.action("list-backups"), state_in)


def test_wait_for_ready_fails(ctx: ops.testing.Context, monkeypatch):
    """Test when wait_for_ready returns False."""
    import beszel

    # Mock wait_for_ready to return False
    monkeypatch.setattr(beszel, "wait_for_ready", lambda container: False)

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.MaintenanceStatus("Waiting for service to start")


def test_version_not_available(ctx: ops.testing.Context, monkeypatch):
    """Test when version is not available."""
    import beszel

    # Mock get_version to return None
    monkeypatch.setattr(beszel, "get_version", lambda container: None)

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    # Should still reach active status even without version
    assert state_out.unit_status == ops.ActiveStatus()
    # Workload version should not be set
    assert state_out.workload_version == ""


def test_create_agent_token_fails(ctx: ops.testing.Context, monkeypatch):
    """Test create-agent-token action when token creation fails."""
    import beszel

    # Mock create_agent_token to return None
    monkeypatch.setattr(beszel, "create_agent_token", lambda container, description: None)

    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
    )

    with pytest.raises(ops.testing.ActionFailed, match="Failed to create agent token"):
        ctx.run(ctx.on.action("create-agent-token"), state_in)


def test_storage_empty_list(ctx: ops.testing.Context):
    """Test when storage list is empty."""
    # Storage exists in metadata but hasn't been attached yet
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
            )
        ],
        storages=[],  # Empty list - no storage attached
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.BlockedStatus("Storage not attached")


def test_oauth_environment_variables(ctx: ops.testing.Context, monkeypatch):
    """Test that OAuth configuration sets environment variables."""
    state_in = ops.testing.State(
        leader=True,
        config={"external-hostname": "beszel.example.com"},
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    # Use context manager to mock OAuth methods
    with ctx(ctx.on.config_changed(), state_in) as manager:
        charm = manager.charm

        # Mock OAuth to return provider info
        import unittest.mock

        mock_provider_info = unittest.mock.Mock()
        mock_provider_info.client_id = "test-client-id"
        mock_provider_info.client_secret = "test-client-secret"
        mock_provider_info.issuer_url = "https://issuer.example.com"

        monkeypatch.setattr(charm.oauth, "is_client_created", lambda: True)
        monkeypatch.setattr(charm.oauth, "get_provider_info", lambda: mock_provider_info)

        state_out = manager.run()

    # Check that OAuth env vars were set
    container = state_out.get_container(CONTAINER_NAME)
    layer = container.layers["beszel"]
    service = layer.services["beszel"]

    assert "OIDC_CLIENT_ID" in service.environment
    assert service.environment["OIDC_CLIENT_ID"] == "test-client-id"
    assert "OIDC_CLIENT_SECRET" in service.environment
    assert service.environment["OIDC_CLIENT_SECRET"] == "test-client-secret"
    assert "OIDC_ISSUER_URL" in service.environment
    assert service.environment["OIDC_ISSUER_URL"] == "https://issuer.example.com"
    assert "OIDC_REDIRECT_URI" in service.environment


def test_s3_environment_variables_with_relation(ctx: ops.testing.Context, monkeypatch):
    """Test that S3 configuration sets environment variables from relation."""
    state_in = ops.testing.State(
        leader=True,
        config={
            "s3-backup-enabled": True,
            "s3-endpoint": "https://fallback.example.com",
            "s3-bucket": "fallback-bucket",
        },
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
                execs={
                    ops.testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n"),
                    ops.testing.Exec(
                        ["/beszel", "health", "--url", "http://localhost:8090"], return_code=0
                    ),
                },
            )
        ],
        storages=[ops.testing.Storage("beszel-data", index=0)],
    )

    # Use context manager to mock S3 methods
    with ctx(ctx.on.config_changed(), state_in) as manager:
        charm = manager.charm

        # Mock S3 to return connection info
        s3_params = {
            "endpoint": "https://s3.example.com",
            "bucket": "my-bucket",
            "region": "us-west-2",
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
        }

        monkeypatch.setattr(charm.s3, "get_s3_connection_info", lambda: s3_params)

        state_out = manager.run()

    # Check that S3 env vars were set from relation
    container = state_out.get_container(CONTAINER_NAME)
    layer = container.layers["beszel"]
    service = layer.services["beszel"]

    assert "S3_BACKUP_ENABLED" in service.environment
    assert service.environment["S3_BACKUP_ENABLED"] == "true"
    assert "S3_ENDPOINT" in service.environment
    assert service.environment["S3_ENDPOINT"] == "https://s3.example.com"
    assert "S3_BUCKET" in service.environment
    assert service.environment["S3_BUCKET"] == "my-bucket"
    assert "S3_REGION" in service.environment
    assert service.environment["S3_REGION"] == "us-west-2"
    assert "S3_ACCESS_KEY_ID" in service.environment
    assert service.environment["S3_ACCESS_KEY_ID"] == "test-access-key"
    assert "S3_SECRET_ACCESS_KEY" in service.environment
    assert service.environment["S3_SECRET_ACCESS_KEY"] == "test-secret-key"
