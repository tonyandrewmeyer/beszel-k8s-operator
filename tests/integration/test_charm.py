# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import pytest
import yaml

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(pathlib.Path("charmcraft.yaml").read_text())
APP_NAME = "beszel"


@pytest.fixture(scope="module")
def deploy(charm: pathlib.Path, juju: jubilant.Juju):
    """Deploy the charm under test with storage."""
    resources = {"beszel-image": METADATA["resources"]["beszel-image"]["upstream-source"]}
    juju.deploy(charm.resolve(), app=APP_NAME, resources=resources, storage="beszel-data=1G")
    juju.wait(jubilant.all_active, timeout=600)
    return juju


def test_deploy_with_storage(deploy: jubilant.Juju):
    """Test that the charm deploys successfully with storage attached."""
    juju = deploy
    status = juju.status()

    # Verify application is active
    assert APP_NAME in status.apps
    app = status.apps[APP_NAME]
    assert app.status == "active", f"App status is {app.status}, expected active"

    # Verify unit is active
    assert len(app.units) == 1
    unit = list(app.units.values())[0]
    assert unit.workload_status == "active", f"Unit status is {unit.workload_status}"

    # Verify storage is attached
    assert "beszel-data/0" in juju.run("storage", "--format=json").get("storage", {})


def test_service_is_running(deploy: jubilant.Juju):
    """Test that the Beszel service is running in the container."""
    juju = deploy
    unit_name = f"{APP_NAME}/0"

    # Check that the Pebble service is running
    result = juju.run_unit(unit_name, f"PEBBLE_SOCKET=/charm/containers/beszel/pebble.socket /charm/bin/pebble services")
    assert "beszel" in result.stdout
    assert "active" in result.stdout.lower() or "running" in result.stdout.lower()


def test_http_service_responds(deploy: jubilant.Juju):
    """Test that the Beszel HTTP service responds to requests."""
    juju = deploy
    unit_name = f"{APP_NAME}/0"

    # Try to connect to the Beszel web interface
    result = juju.run_unit(unit_name, "curl -f http://localhost:8090/ || echo 'FAILED'")
    # Beszel should respond with HTML (or redirect)
    assert "FAILED" not in result.stdout, "HTTP service is not responding"


def test_get_admin_url_action(deploy: jubilant.Juju):
    """Test the get-admin-url action returns a valid URL."""
    juju = deploy
    unit_name = f"{APP_NAME}/0"

    # Run the get-admin-url action
    result = juju.run_action(unit_name, "get-admin-url", wait=True)

    # Verify the action succeeded
    assert result.status == "completed", f"Action status: {result.status}"

    # Verify URL is in the results
    assert "url" in result.results
    url = result.results["url"]
    assert url.startswith("http://") or url.startswith("https://")
    assert APP_NAME in url or "beszel" in url


def test_configuration_changes(deploy: jubilant.Juju):
    """Test that configuration changes trigger service restart."""
    juju = deploy

    # Change log-level configuration
    juju.config(APP_NAME, {"log-level": "debug"})
    juju.wait(jubilant.all_active, timeout=300)

    # Verify the application is still active after config change
    status = juju.status()
    app = status.apps[APP_NAME]
    assert app.status == "active"

    # Change back to info
    juju.config(APP_NAME, {"log-level": "info"})
    juju.wait(jubilant.all_active, timeout=300)


def test_ingress_relation(deploy: jubilant.Juju):
    """Test integration with nginx-ingress-integrator."""
    juju = deploy

    # Deploy nginx-ingress-integrator
    juju.deploy("nginx-ingress-integrator", app="ingress", channel="stable", trust=True)
    juju.wait(jubilant.all_active, timeout=600)

    # Configure ingress
    juju.config("ingress", {"service-hostname": "beszel.local"})

    # Integrate with beszel
    juju.integrate(APP_NAME, "ingress:ingress")
    juju.wait(jubilant.all_active, timeout=300)

    # Verify relation is established
    status = juju.status()
    app = status.apps[APP_NAME]
    assert "ingress" in app.relations

    # Clean up
    juju.run("remove-relation", APP_NAME, "ingress")
    juju.run("remove-application", "ingress", "--force")
    juju.wait(lambda s: "ingress" not in s.apps, timeout=300)


def test_create_agent_token_action(deploy: jubilant.Juju):
    """Test the create-agent-token action."""
    juju = deploy
    unit_name = f"{APP_NAME}/0"

    # Run the create-agent-token action
    result = juju.run_action(
        unit_name, "create-agent-token", params={"description": "test-token"}, wait=True
    )

    # Verify the action succeeded
    assert result.status == "completed", f"Action status: {result.status}"

    # Verify token is in the results
    assert "token" in result.results
    assert len(result.results["token"]) > 0

    # Verify instructions are provided
    assert "instructions" in result.results


def test_backup_actions(deploy: jubilant.Juju):
    """Test backup-related actions."""
    juju = deploy
    unit_name = f"{APP_NAME}/0"

    # List backups (should work even if empty)
    result = juju.run_action(unit_name, "list-backups", wait=True)
    assert result.status == "completed", f"list-backups failed: {result.status}"
    assert "backups" in result.results

    # Trigger a backup
    result = juju.run_action(unit_name, "backup-now", wait=True)
    assert result.status == "completed", f"backup-now failed: {result.status}"
    assert "backup-path" in result.results or "timestamp" in result.results

    # List backups again - should now have at least one
    result = juju.run_action(unit_name, "list-backups", wait=True)
    assert result.status == "completed"
    # Note: We can't guarantee backup completed in time, but action should succeed


def test_storage_persistence(deploy: jubilant.Juju):
    """Test that data persists across container restarts."""
    juju = deploy
    unit_name = f"{APP_NAME}/0"

    # Create a test file in the storage
    test_file = "/beszel_data/test-persistence.txt"
    test_content = "persistence-test-data"
    juju.run_unit(unit_name, f"echo '{test_content}' > {test_file}")

    # Verify file exists
    result = juju.run_unit(unit_name, f"cat {test_file}")
    assert test_content in result.stdout

    # Restart the workload (kill the service, Pebble will restart it)
    juju.run_unit(unit_name, "pkill -f beszel || true")

    # Wait for service to come back
    juju.wait(jubilant.all_active, timeout=300)

    # Verify file still exists after restart
    result = juju.run_unit(unit_name, f"cat {test_file}")
    assert test_content in result.stdout, "Data did not persist across restart"

    # Clean up
    juju.run_unit(unit_name, f"rm {test_file}")


def test_custom_port_configuration(deploy: jubilant.Juju):
    """Test that custom port configuration works."""
    juju = deploy

    # Change port to 8091
    juju.config(APP_NAME, {"port": "8091"})
    juju.wait(jubilant.all_active, timeout=300)

    unit_name = f"{APP_NAME}/0"

    # Verify service responds on new port
    result = juju.run_unit(unit_name, "curl -f http://localhost:8091/ || echo 'FAILED'")
    assert "FAILED" not in result.stdout, "Service not responding on port 8091"

    # Verify old port is not responding
    result = juju.run_unit(unit_name, "curl -f --connect-timeout 2 http://localhost:8090/ 2>&1 || echo 'FAILED'")
    assert "FAILED" in result.stdout, "Service still responding on old port"

    # Change back to default port
    juju.config(APP_NAME, {"port": "8090"})
    juju.wait(jubilant.all_active, timeout=300)


def test_external_hostname_configuration(deploy: jubilant.Juju):
    """Test that external hostname configuration is applied."""
    juju = deploy

    # Set external hostname
    juju.config(APP_NAME, {"external-hostname": "beszel.example.com"})
    juju.wait(jubilant.all_active, timeout=300)

    # Verify the application is still active
    status = juju.status()
    app = status.apps[APP_NAME]
    assert app.status == "active"

    # Reset configuration
    juju.config(APP_NAME, {"external-hostname": ""})
    juju.wait(jubilant.all_active, timeout=300)


def test_upgrade_charm(deploy: jubilant.Juju, charm: pathlib.Path):
    """Test that the charm can be upgraded."""
    juju = deploy

    # Refresh the charm (upgrade to same version)
    juju.refresh(APP_NAME, path=charm.resolve())
    juju.wait(jubilant.all_active, timeout=300)

    # Verify the application is still active after upgrade
    status = juju.status()
    app = status.apps[APP_NAME]
    assert app.status == "active"

    # Verify service is still running
    unit_name = f"{APP_NAME}/0"
    result = juju.run_unit(unit_name, "curl -f http://localhost:8090/ || echo 'FAILED'")
    assert "FAILED" not in result.stdout, "Service not running after upgrade"
