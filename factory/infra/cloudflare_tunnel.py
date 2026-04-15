"""
AI Factory Pipeline v5.8 — Cloudflare Tunnel Client

Manages a cloudflared tunnel that exposes the local pipeline webhook
to the internet without a public IP address. Enables LOCAL and HYBRID
execution modes where the pipeline runs on the operator's machine.

This is FREE — Cloudflare Tunnel has no usage limits on the free plan.

How it works:
  1. cloudflared binary runs locally
  2. Establishes an encrypted tunnel to Cloudflare's edge
  3. Returns a public HTTPS URL (e.g., https://random.trycloudflare.com)
  4. Telegram webhook callbacks reach the local pipeline via this URL

Usage:
  tunnel = CloudflareTunnelClient()
  url = await tunnel.start(local_port=8765)
  # → "https://abc123.trycloudflare.com"

Config (optional, for named tunnels):
  CLOUDFLARE_API_TOKEN=your_token
  CLOUDFLARE_TUNNEL_NAME=ai-factory-pipeline

Spec Authority: v5.6 §2.4.1 (Local/Hybrid mode)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from typing import Optional

logger = logging.getLogger("factory.infra.cloudflare_tunnel")

_CLOUDFLARED_URL_RE = re.compile(
    r"https://[a-z0-9\-]+\.trycloudflare\.com|https://[a-z0-9\-]+\.cfargotunnel\.com"
)
_STARTUP_TIMEOUT = 30  # seconds to wait for tunnel URL


class CloudflareTunnelClient:
    """Manage a cloudflared tunnel for local pipeline execution.

    Supports both:
      • Quick tunnels (no login, random URL, free, always works)
      • Named tunnels (requires CLOUDFLARE_API_TOKEN, stable URL)
    """

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._tunnel_url: Optional[str] = None
        self._local_port: int = 8765
        self._api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        self._tunnel_name = os.getenv("CLOUDFLARE_TUNNEL_NAME", "ai-factory-pipeline")

    @property
    def tunnel_url(self) -> Optional[str]:
        return self._tunnel_url

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── Installation Check ──────────────────────────────────────────

    @staticmethod
    async def check_installed() -> bool:
        """Check if cloudflared binary is installed."""
        try:
            result = subprocess.run(
                ["cloudflared", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def get_install_instructions() -> str:
        return (
            "cloudflared not found. Install it:\n"
            "  macOS:  brew install cloudflare/cloudflare/cloudflared\n"
            "  Linux:  wget https://github.com/cloudflare/cloudflared/releases/"
            "latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && "
            "chmod +x /usr/local/bin/cloudflared\n"
            "  Windows: winget install --id Cloudflare.cloudflared\n"
            "  Docs: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/"
        )

    # ── Quick Tunnel (no auth, random URL) ──────────────────────────

    async def start_quick(self, local_port: int = 8765) -> Optional[str]:
        """Start a quick tunnel (no login required, random URL).

        This is the zero-config free option. URL changes each restart.
        Suitable for development and ad-hoc sessions.
        """
        if not await self.check_installed():
            raise RuntimeError(self.get_install_instructions())

        self._local_port = local_port
        cmd = [
            "cloudflared", "tunnel", "--url",
            f"http://localhost:{local_port}",
            "--no-autoupdate",
        ]

        logger.info(f"[cloudflare-tunnel] Starting quick tunnel on port {local_port}")
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Read output to find the URL
        self._tunnel_url = await asyncio.get_event_loop().run_in_executor(
            None, self._parse_url_from_output, _STARTUP_TIMEOUT,
        )

        if self._tunnel_url:
            logger.info(f"[cloudflare-tunnel] Public URL: {self._tunnel_url}")
        else:
            logger.error("[cloudflare-tunnel] Failed to get tunnel URL")
            await self.stop()

        return self._tunnel_url

    def _parse_url_from_output(self, timeout: float) -> Optional[str]:
        """Read cloudflared stdout until we find the public URL."""
        if not self._proc or not self._proc.stdout:
            return None
        deadline = time.time() + timeout
        for line in self._proc.stdout:
            if time.time() > deadline:
                break
            m = _CLOUDFLARED_URL_RE.search(line)
            if m:
                return m.group(0)
        return None

    # ── Named Tunnel (requires API token, stable URL) ───────────────

    async def start_named(self, local_port: int = 8765) -> Optional[str]:
        """Start a named tunnel with a persistent subdomain.

        Requires CLOUDFLARE_API_TOKEN and prior setup:
          cloudflared tunnel login
          cloudflared tunnel create ai-factory-pipeline
          cloudflared tunnel route dns ai-factory-pipeline pipeline.yourdomain.com
        """
        if not self._api_token:
            logger.info("[cloudflare-tunnel] No API token — falling back to quick tunnel")
            return await self.start_quick(local_port)

        config_path = os.path.expanduser("~/.cloudflared/config.yml")
        if not os.path.exists(config_path):
            logger.info("[cloudflare-tunnel] No named tunnel config — falling back to quick tunnel")
            return await self.start_quick(local_port)

        self._local_port = local_port
        cmd = ["cloudflared", "tunnel", "--config", config_path, "run", self._tunnel_name]

        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        # Named tunnel URL is the configured hostname
        # Return the expected URL from config
        self._tunnel_url = await self._read_named_tunnel_url()
        logger.info(f"[cloudflare-tunnel] Named tunnel started: {self._tunnel_url}")
        return self._tunnel_url

    async def _read_named_tunnel_url(self) -> Optional[str]:
        """Extract the hostname from cloudflared config or return None."""
        try:
            import yaml  # optional: pip install pyyaml
            config_path = os.path.expanduser("~/.cloudflared/config.yml")
            with open(config_path) as f:
                config = yaml.safe_load(f)
            ingress = config.get("ingress", [])
            if ingress:
                hostname = ingress[0].get("hostname", "")
                if hostname:
                    return f"https://{hostname}"
        except Exception:
            pass
        return None

    # ── Unified Start ────────────────────────────────────────────────

    async def start(self, local_port: int = 8765) -> Optional[str]:
        """Start the best available tunnel type.

        Named tunnel if API token + config exist, else quick tunnel.
        """
        if self._api_token:
            return await self.start_named(local_port)
        return await self.start_quick(local_port)

    # ── Stop ─────────────────────────────────────────────────────────

    async def stop(self) -> None:
        """Terminate the cloudflared process."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._tunnel_url = None
        logger.info("[cloudflare-tunnel] Tunnel stopped")

    # ── Context manager ──────────────────────────────────────────────

    async def __aenter__(self) -> "CloudflareTunnelClient":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()


# ── Singleton ────────────────────────────────────────────────────────

_tunnel_instance: Optional[CloudflareTunnelClient] = None


def get_tunnel() -> CloudflareTunnelClient:
    global _tunnel_instance
    if _tunnel_instance is None:
        _tunnel_instance = CloudflareTunnelClient()
    return _tunnel_instance
