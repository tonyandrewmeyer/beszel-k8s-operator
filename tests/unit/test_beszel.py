# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

import pathlib

import pytest
from ops import testing

import beszel
from charm import BeszelCharm

CONTAINER_NAME = "beszel"


@pytest.fixture
def container_with_data(tmp_path: pathlib.Path):
    """Yield a connected workload container backed by a real temp directory."""
    ctx = testing.Context(BeszelCharm)
    container = testing.Container(
        name=CONTAINER_NAME,
        can_connect=True,
        mounts={"beszel-data": testing.Mount(location="/beszel_data", source=str(tmp_path))},
        execs={testing.Exec(["/beszel", "--version"], stdout="beszel version 0.17.0\n")},
    )
    state_in = testing.State(leader=True, containers={container})
    with ctx(ctx.on.update_status(), state_in) as manager:
        yield manager.charm.container, tmp_path


def test_get_version(container_with_data):
    container, _ = container_with_data
    assert beszel.get_version(container) == "0.17.0"


def test_get_version_empty(tmp_path: pathlib.Path):
    ctx = testing.Context(BeszelCharm)
    container = testing.Container(
        name=CONTAINER_NAME,
        can_connect=True,
        execs={testing.Exec(["/beszel", "--version"], stdout="\n")},
    )
    with ctx(ctx.on.update_status(), testing.State(containers={container})) as manager:
        assert beszel.get_version(manager.charm.container) is None


def test_create_agent_token(container_with_data):
    container, data_dir = container_with_data
    (data_dir / "data.db").write_text("db")

    token = beszel.create_agent_token(container, "my-agent")

    assert token is not None
    assert len(token) > 0


def test_create_agent_token_no_database(container_with_data):
    container, _ = container_with_data
    assert beszel.create_agent_token(container) is None


def test_create_backup(container_with_data):
    container, data_dir = container_with_data
    (data_dir / "data.db").write_text("db-contents")

    info = beszel.create_backup(container)

    assert info is not None
    assert info["filename"].startswith("beszel-backup-")
    assert (data_dir / "backups" / info["filename"]).read_text() == "db-contents"


def test_create_backup_no_database(container_with_data):
    container, _ = container_with_data
    assert beszel.create_backup(container) is None


def test_list_backups_empty(container_with_data):
    container, _ = container_with_data
    assert beszel.list_backups(container) == []


def test_list_backups(container_with_data):
    container, data_dir = container_with_data
    backups = data_dir / "backups"
    backups.mkdir()
    (backups / "beszel-backup-20250101-120000.db").write_text("a")
    (backups / "ignore.txt").write_text("b")

    result = beszel.list_backups(container)

    assert len(result) == 1
    assert result[0]["filename"] == "beszel-backup-20250101-120000.db"
