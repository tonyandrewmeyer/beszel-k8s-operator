# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

import ops
import pytest
from ops import testing

from charm import BeszelCharm

CONTAINER_NAME = "beszel"

# A version exec that lets the charm reach ActiveStatus.
VERSION_EXEC = {testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n")}


@pytest.fixture
def ctx():
    """Create a testing context that autoloads metadata from charmcraft.yaml."""
    return testing.Context(BeszelCharm)


def _container(can_connect: bool = True, *, with_storage: bool = True, execs=None):
    """Build a container, optionally with the data storage mounted and execs set."""
    kwargs = {}
    if with_storage:
        kwargs["mounts"] = {"beszel-data": testing.Mount(location="/beszel_data", source="/tmp")}
    if execs is not None:
        kwargs["execs"] = execs
    return testing.Container(name=CONTAINER_NAME, can_connect=can_connect, **kwargs)


def test_pebble_ready_without_storage(ctx: testing.Context):
    state_in = testing.State(leader=True, containers={_container(with_storage=False)})

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.BlockedStatus("Storage not attached")


def test_container_not_ready(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        containers={_container(can_connect=False)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.WaitingStatus("Waiting for Pebble")


def test_pebble_ready_with_storage(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.ActiveStatus()
    service = state_out.get_container(CONTAINER_NAME).layers["beszel"].services["beszel"]
    assert service.command == "/beszel serve"
    assert service.startup == "enabled"
    assert service.environment["PORT"] == "8090"


def test_config_changed_updates_service(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        config={"port": 8091, "log-level": "debug"},
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    assert state_out.unit_status == ops.ActiveStatus()
    service = state_out.get_container(CONTAINER_NAME).layers["beszel"].services["beszel"]
    assert service.environment["PORT"] == "8091"
    assert service.environment["LOG_LEVEL"] == "DEBUG"


def test_invalid_port_blocks(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        config={"port": 70000},
        containers={_container()},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    assert state_out.unit_status.name == "blocked"
    assert "Invalid configuration" in state_out.unit_status.message


def test_health_check_configuration(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    check = state_out.get_container(CONTAINER_NAME).layers["beszel"].checks["beszel-ready"]
    assert check.level == ops.pebble.CheckLevel.READY
    assert check.http == {"url": "http://localhost:8090/"}
    assert check.period == "10s"
    assert check.threshold == 3


def test_workload_version_set(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        containers={
            _container(
                execs={testing.Exec(["/beszel", "--version"], stdout="beszel version 1.2.3\n")}
            )
        },
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.workload_version == "1.2.3"


def test_version_not_available(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import beszel

    monkeypatch.setattr(beszel, "get_version", lambda container: None)
    state_in = testing.State(
        leader=True,
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.pebble_ready(state_in.get_container(CONTAINER_NAME)), state_in)

    assert state_out.unit_status == ops.ActiveStatus()
    assert state_out.workload_version == ""


def test_upgrade_charm_reconfigures(ctx: testing.Context):
    state_in = testing.State(
        leader=True,
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    state_out = ctx.run(ctx.on.upgrade_charm(), state_in)

    assert state_out.unit_status == ops.ActiveStatus()
    assert "beszel" in state_out.get_container(CONTAINER_NAME).layers


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, "http://beszel:8090"),
        ({"external-hostname": "beszel.example.com"}, "https://beszel.example.com"),
    ],
)
def test_get_admin_url_action(ctx: testing.Context, config: dict, expected: str):
    state_in = testing.State(leader=True, config=config, containers={_container()})

    ctx.run(ctx.on.action("get-admin-url"), state_in)

    assert ctx.action_results == {"url": expected}


def test_create_agent_token_action(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import beszel

    monkeypatch.setattr(beszel, "create_agent_token", lambda container, description: "fake-token")
    state_in = testing.State(leader=True, containers={_container()})

    ctx.run(ctx.on.action("create-agent-token", params={"description": "test"}), state_in)

    results = ctx.action_results
    assert results is not None
    assert results["token"] == "fake-token"
    assert "HUB_URL" in results["instructions"]


def test_create_agent_token_action_failure(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import beszel

    monkeypatch.setattr(beszel, "create_agent_token", lambda container, description: None)
    state_in = testing.State(leader=True, containers={_container()})

    with pytest.raises(testing.ActionFailed, match="Failed to create agent token"):
        ctx.run(ctx.on.action("create-agent-token"), state_in)


def test_backup_now_action(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import beszel

    monkeypatch.setattr(
        beszel,
        "create_backup",
        lambda container: {"backup-path": "/beszel_data/backups/b.db", "timestamp": "t"},
    )
    state_in = testing.State(leader=True, containers={_container()})

    ctx.run(ctx.on.action("backup-now"), state_in)

    assert ctx.action_results == {"backup-path": "/beszel_data/backups/b.db", "timestamp": "t"}


def test_backup_now_action_failure(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import beszel

    monkeypatch.setattr(beszel, "create_backup", lambda container: None)
    state_in = testing.State(leader=True, containers={_container()})

    with pytest.raises(testing.ActionFailed, match="Failed to create backup"):
        ctx.run(ctx.on.action("backup-now"), state_in)


def test_list_backups_action(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import beszel

    backups = [{"filename": "b.db", "path": "/p", "size": "1", "modified": ""}]
    monkeypatch.setattr(beszel, "list_backups", lambda container: backups)
    state_in = testing.State(leader=True, containers={_container()})

    ctx.run(ctx.on.action("list-backups"), state_in)

    assert ctx.action_results == {"backups": backups}


@pytest.mark.parametrize("action", ["create-agent-token", "backup-now", "list-backups"])
def test_action_container_not_ready(ctx: testing.Context, action: str):
    state_in = testing.State(leader=True, containers={_container(can_connect=False)})

    with pytest.raises(testing.ActionFailed, match="Container not ready"):
        ctx.run(ctx.on.action(action), state_in)


@pytest.mark.parametrize(
    ("config", "is_none"),
    [({}, True), ({"external-hostname": "beszel.example.com"}, False)],
)
def test_oauth_client_config(ctx: testing.Context, config: dict, is_none: bool):
    state_in = testing.State(leader=True, config=config, containers={_container()})

    with ctx(ctx.on.install(), state_in) as manager:
        client_config = manager.charm._get_oauth_client_config()
        manager.run()

    assert (client_config is None) is is_none
    if client_config is not None:
        assert "beszel.example.com" in client_config.redirect_uri
        assert "openid" in client_config.scope


def test_oauth_environment_variables(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    import unittest.mock

    state_in = testing.State(
        leader=True,
        config={"external-hostname": "beszel.example.com"},
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    with ctx(ctx.on.config_changed(), state_in) as manager:
        provider_info = unittest.mock.Mock()
        provider_info.client_id = "test-client-id"
        provider_info.client_secret = "test-client-secret"
        provider_info.issuer_url = "https://issuer.example.com"
        monkeypatch.setattr(manager.charm.oauth, "is_client_created", lambda: True)
        monkeypatch.setattr(manager.charm.oauth, "get_provider_info", lambda: provider_info)
        state_out = manager.run()

    env = state_out.get_container(CONTAINER_NAME).layers["beszel"].services["beszel"].environment
    assert env["OIDC_CLIENT_ID"] == "test-client-id"
    assert env["OIDC_CLIENT_SECRET"] == "test-client-secret"
    assert env["OIDC_ISSUER_URL"] == "https://issuer.example.com"
    assert "OIDC_REDIRECT_URI" in env


def test_s3_environment_variables(ctx: testing.Context, monkeypatch: pytest.MonkeyPatch):
    state_in = testing.State(
        leader=True,
        config={"s3-backup-enabled": True},
        containers={_container(execs=VERSION_EXEC)},
        storages={testing.Storage("beszel-data", index=0)},
    )

    s3_params = {
        "endpoint": "https://s3.example.com",
        "bucket": "my-bucket",
        "region": "us-west-2",
        "access-key": "test-access-key",
        "secret-key": "test-secret-key",
    }
    with ctx(ctx.on.config_changed(), state_in) as manager:
        monkeypatch.setattr(manager.charm.s3, "get_s3_connection_info", lambda: s3_params)
        state_out = manager.run()

    env = state_out.get_container(CONTAINER_NAME).layers["beszel"].services["beszel"].environment
    assert env["S3_BACKUP_ENABLED"] == "true"
    assert env["S3_ENDPOINT"] == "https://s3.example.com"
    assert env["S3_BUCKET"] == "my-bucket"
    assert env["S3_REGION"] == "us-west-2"
    assert env["S3_ACCESS_KEY_ID"] == "test-access-key"
    assert env["S3_SECRET_ACCESS_KEY"] == "test-secret-key"
