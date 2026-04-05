"""
AI Factory Pipeline v5.6 — User-Space Enforcer (Zero Sudo)

Implements:
  - §2.5 User-Space Enforcer (prohibited patterns + safe rewrites)
  - ADR-012: Zero sudo — user-space only

Every command the pipeline generates passes through enforce_user_space()
before execution. This is a hard security boundary.

Spec Authority: v5.6 §2.5, ADR-012
"""

from __future__ import annotations

import logging
import os

from factory.core.state import UserSpaceViolation

logger = logging.getLogger("factory.core.user_space")


# ═══════════════════════════════════════════════════════════════════
# §2.5 Prohibited Patterns
# ═══════════════════════════════════════════════════════════════════

PROHIBITED_PATTERNS: list[str] = [
    # Privilege escalation (§2.5)
    "sudo ",
    "sudo\t",
    "su -",
    "su root",
    "pkexec",
    "doas ",
    # Dangerous file permissions
    "chmod 777",
    "chmod +s",
    "chown root",
    # System path manipulation
    "/usr/sbin/",
    "rm -rf /",
    "dd if=",
    # Disk / device attacks
    "mkfs.",
    "fdisk ",
    "> /dev/sd",
    "> /dev/nvme",
    # Network / firewall manipulation
    "iptables -f",
    "iptables -flush",
    # Boot / system tampering
    "shutdown -h",
    "reboot ",
    "init 0",
    "init 6",
    # Process / kernel access
    "echo 1 > /proc/sysrq",
]

# ═══════════════════════════════════════════════════════════════════
# §2.5 Safe Install Rewrites
# ═══════════════════════════════════════════════════════════════════

SAFE_INSTALL_REWRITES: dict[str, str] = {
    "pip install": "pip install --user",
    "npm install -g": "npx",
}

# ═══════════════════════════════════════════════════════════════════
# §2.5 Prohibited File Paths
# ═══════════════════════════════════════════════════════════════════

PROHIBITED_PATH_PREFIXES: list[str] = [
    "/usr/",
    "/etc/",
    "/var/",
    "/bin/",
    "/sbin/",
    "/boot/",
    "/root/",
    "/System/",
    "/Library/",
]

ALLOWED_PATH_PREFIXES: list[str] = [
    os.path.expanduser("~"),
    "/tmp/",
    "/Users/",
    "/home/",
]


def enforce_user_space(command: str) -> str:
    """Validate and sanitize a command for user-space execution.

    Spec: §2.5
    Blocks prohibited patterns (sudo, su, chmod 777, etc.).
    Rewrites global installs to user-space equivalents.

    Args:
        command: The command string to validate.

    Returns:
        Sanitized command string (with rewrites applied).

    Raises:
        UserSpaceViolation: If prohibited pattern detected.
    """
    command_lower = command.lower().strip()

    # Check prohibited patterns
    for pattern in PROHIBITED_PATTERNS:
        if pattern in command_lower:
            raise UserSpaceViolation(
                f"Prohibited pattern '{pattern}' in command: "
                f"{command[:100]}"
            )

    # Apply safe rewrites for global installs
    for old, new in SAFE_INSTALL_REWRITES.items():
        if old in command and new not in command:
            original = command
            command = command.replace(old, new)
            logger.info(
                f"[User-Space] Rewrote: '{old}' → '{new}' "
                f"in: {original[:80]}"
            )

    return command


def validate_file_path(path: str) -> None:
    """Validate that a file path is within allowed directories.

    Spec: §2.5
    Prevents writing to system directories.

    Args:
        path: File path to validate.

    Raises:
        UserSpaceViolation: If path is outside allowed directories.
    """
    abs_path = os.path.abspath(path)

    # Check prohibited prefixes
    for prefix in PROHIBITED_PATH_PREFIXES:
        if abs_path.startswith(prefix):
            # Check if it's actually within an allowed sub-path
            is_allowed = any(
                abs_path.startswith(allowed)
                for allowed in ALLOWED_PATH_PREFIXES
            )
            if not is_allowed:
                raise UserSpaceViolation(
                    f"File path '{path}' resolves to prohibited "
                    f"directory: {abs_path}"
                )


def sanitize_for_shell(value: str) -> str:
    """Sanitize a value for safe shell interpolation.

    Prevents shell injection by escaping special characters.

    Args:
        value: String to sanitize.

    Returns:
        Shell-safe string.
    """
    # Remove or escape dangerous shell characters
    dangerous = [";", "&", "|", "`", "$", "(", ")", "{", "}", "<", ">", "\\"]
    result = value
    for char in dangerous:
        result = result.replace(char, f"\\{char}")
    return result