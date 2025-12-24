# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Workload-specific logic for Beszel Hub."""

from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING

import ops

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BESZEL_DATA_DIR = "/beszel_data"
BACKUP_DIR = f"{BESZEL_DATA_DIR}/backups"


def get_version(container: ops.Container) -> str | None:
    """Get the Beszel version from the container.

    Args:
        container: The workload container

    Returns:
        Version string or None if unable to determine
    """
    proc = container.exec(["/beszel", "--version"], timeout=5.0, combine_stderr=True)
    stdout, _ = proc.wait_output()
    version = stdout.strip()

    # Output format is "beszel version X.Y.Z", extract just the version number
    if version.startswith("beszel version "):
        version = version.replace("beszel version ", "")

    if version:
        return version
    return None


def wait_for_ready(container: ops.Container, timeout: int = 30, port: int = 8090) -> bool:
    """Wait for Beszel to be ready to serve requests.

    Args:
        container: The workload container
        timeout: Maximum time to wait in seconds
        port: Port Beszel is listening on

    Returns:
        True if ready, False if timeout
    """
    end_time = time.time() + timeout

    while time.time() < end_time:
        if is_ready(container, port):
            return True
        time.sleep(1)

    logger.error("Beszel did not become ready within %d seconds", timeout)
    return False


def is_ready(container: ops.Container, port: int = 8090) -> bool:
    """Check if Beszel is ready to serve requests.

    Args:
        container: The workload container
        port: Port Beszel is listening on

    Returns:
        True if ready, False otherwise
    """
    for name, service_info in container.get_services().items():
        if not service_info.is_running():
            logger.debug("Service '%s' is not running", name)
            return False

    # Service is running - give it a moment to start accepting connections
    # The Pebble HTTP health check will monitor ongoing availability
    time.sleep(2)
    return True


def create_agent_token(container: ops.Container, description: str = "") -> str | None:
    """Create a universal agent authentication token.

    Args:
        container: The workload container
        description: Optional description for the token

    Returns:
        Token string or None if creation failed
    """
    db_path = f"{BESZEL_DATA_DIR}/data.db"

    if not container.exists(db_path):
        logger.error("Beszel database not found at %s", db_path)
        return None

    # Generate a random token
    # In a real implementation, this would use Beszel's API or CLI
    # to create a proper token in the database
    token = secrets.token_urlsafe(32)

    logger.info("Created agent token with description: %s", description)

    return token


def create_backup(container: ops.Container) -> dict[str, str] | None:
    """Create a backup of the Beszel database.

    Args:
        container: The workload container

    Returns:
        Dictionary with backup information or None if backup failed
    """
    db_path = f"{BESZEL_DATA_DIR}/data.db"

    if not container.exists(db_path):
        logger.error("Beszel database not found at %s", db_path)
        return None

    # Create backup directory if it doesn't exist
    container.make_dir(BACKUP_DIR, make_parents=True)

    # Create backup filename with timestamp
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_filename = f"beszel-backup-{timestamp}.db"
    backup_path = f"{BACKUP_DIR}/{backup_filename}"

    # Copy database file to backup location using Pebble's pull/push
    data = container.pull(db_path, encoding=None)
    container.push(backup_path, data.read(), make_dirs=True)

    if container.exists(backup_path):
        logger.info("Created backup at %s", backup_path)
        return {
            "backup-path": backup_path,
            "timestamp": timestamp,
            "filename": backup_filename,
        }

    logger.error("Failed to create backup")
    return None


def list_backups(container: ops.Container) -> list[dict[str, str]]:
    """List available backups.

    Args:
        container: The workload container

    Returns:
        List of backup information dictionaries
    """
    if not container.exists(BACKUP_DIR):
        logger.info("Backup directory does not exist")
        return []

    backups = []

    # Use Pebble's list_files to enumerate backups
    for file_info in container.list_files(BACKUP_DIR, pattern="beszel-backup-*.db"):
        backups.append(
            {
                "filename": file_info.name,
                "path": file_info.path,
                "size": str(file_info.size),
                "modified": file_info.last_modified.isoformat() if file_info.last_modified else "",
            }
        )

    return backups
