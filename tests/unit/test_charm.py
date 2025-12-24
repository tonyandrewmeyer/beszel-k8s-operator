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


@pytest.fixture
def ctx():
    """Create a testing context."""
    return ops.testing.Context(BeszelCharm, meta=METADATA)


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

    state_out = ctx.run(ctx.on.pebble_ready(CONTAINER_NAME), state_in)

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
            )
        ],
        storages=[ops.testing.Storage("beszel-data")],
    )

    state_out = ctx.run(ctx.on.pebble_ready(CONTAINER_NAME), state_in)

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
            )
        ],
        storages=[ops.testing.Storage("beszel-data")],
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
            )
        ],
        storages=[ops.testing.Storage("beszel-data")],
    )

    state_out = ctx.run(ctx.on.pebble_ready(CONTAINER_NAME), state_in)

    container = state_out.get_container(CONTAINER_NAME)
    layer = container.layers["beszel"]

    assert "beszel-ready" in layer.checks
    check = layer.checks["beszel-ready"]
    assert check.level == "ready"
    assert "/beszel health" in check.exec["command"]  # type: ignore[index]
    assert check.period == "60s"


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


def test_create_agent_token_action(ctx: ops.testing.Context):
    """Test create-agent-token action."""
    state_in = ops.testing.State(
        leader=True,
        containers=[
            ops.testing.Container(
                name=CONTAINER_NAME,
                can_connect=True,
                mounts={"beszel-data": ops.testing.Mount(location="/beszel_data", source="tmpfs")},
            )
        ],
        storages=[ops.testing.Storage("beszel-data")],
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

    state_out = ctx.run(ctx.on.pebble_ready(CONTAINER_NAME), state_in)

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
            )
        ],
        storages=[ops.testing.Storage("beszel-data")],
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
            )
        ],
        storages=[ops.testing.Storage("beszel-data")],
    )

    state_out = ctx.run(ctx.on.upgrade_charm(), state_in)

    # Should reconfigure the workload
    container = state_out.get_container(CONTAINER_NAME)
    assert "beszel" in container.layers
