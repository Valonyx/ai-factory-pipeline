"""Tests for factory.delivery (P8 Delivery)."""

import os
import pytest
from factory.delivery.file_delivery import (
    compute_sha256, upload_to_temp_storage, send_telegram_file,
    TELEGRAM_FILE_LIMIT_MB, STORAGE_BUCKET,
)
from factory.delivery.airlock import (
    airlock_deliver, get_airlock_summary,
    AIRLOCK_DISCLAIMER, PLATFORM_EXTENSIONS,
)
from factory.delivery.app_store import attempt_store_upload
from factory.delivery.handoff_docs import (
    generate_handoff_intelligence_pack,
    PER_PROJECT_DOCS, PER_PROGRAM_DOCS,
)


class TestFileDelivery:
    def test_sha256(self, tmp_binary):
        sha = compute_sha256(tmp_binary)
        assert len(sha) == 64
        assert sha == compute_sha256(tmp_binary)

    @pytest.mark.asyncio
    async def test_upload_stub(self, tmp_binary):
        url = await upload_to_temp_storage(tmp_binary, "proj-001")
        # No storage backend in test env — graceful degradation returns local:// path
        assert url.startswith("local://") or "proj-001" in url or "storage" in url

    @pytest.mark.asyncio
    async def test_send_small_file(self, tmp_binary):
        result = await send_telegram_file("op1", tmp_binary, "proj-001")
        assert result["method"] == "telegram_direct"

    def test_constants(self):
        assert TELEGRAM_FILE_LIMIT_MB == 50
        assert STORAGE_BUCKET == "build-artifacts"


class TestAirlock:
    @pytest.mark.asyncio
    async def test_airlock_deliver(self, fresh_state, tmp_binary):
        result = await airlock_deliver(
            fresh_state, "ios", tmp_binary, "Code signing expired",
        )
        assert result["method"] == "telegram"

    @pytest.mark.asyncio
    async def test_airlock_missing_binary(self, fresh_state):
        result = await airlock_deliver(
            fresh_state, "android", "/nonexistent.aab", "API error",
        )
        assert result["method"] == "error"

    def test_disclaimer(self):
        assert "Manual upload does not bypass" in AIRLOCK_DISCLAIMER

    def test_platform_extensions(self):
        assert PLATFORM_EXTENSIONS["ios"] == ".ipa"
        assert PLATFORM_EXTENSIONS["android"] == ".aab"

    def test_airlock_summary(self, fresh_state):
        s = get_airlock_summary(fresh_state)
        assert s["total_deliveries"] == 0


class TestAppStore:
    @pytest.mark.asyncio
    async def test_ios_missing_creds(self, fresh_state, tmp_ipa):
        os.environ.pop("APP_STORE_API_KEY", None)
        result = await attempt_store_upload(fresh_state, "ios", tmp_ipa)
        assert result["success"] is False
        assert result["method"] == "airlock"

    @pytest.mark.asyncio
    async def test_ios_stub_success(self, fresh_state, tmp_ipa):
        from unittest.mock import patch, AsyncMock
        os.environ["APP_STORE_API_KEY"] = "test"
        os.environ["APP_STORE_ISSUER_ID"] = "test"
        # Mock the subprocess calls so altool doesn't run in test env
        mock_cmd_result = {"exit_code": 0, "stdout": "{}", "stderr": ""}
        with patch("factory.delivery.app_store._run_command", new=AsyncMock(return_value=mock_cmd_result)):
            result = await attempt_store_upload(fresh_state, "ios", tmp_ipa)
        assert result["success"] is True
        os.environ.pop("APP_STORE_API_KEY", None)
        os.environ.pop("APP_STORE_ISSUER_ID", None)


class TestHandoffDocs:
    def test_doc_templates(self):
        assert len(PER_PROJECT_DOCS) == 4
        assert len(PER_PROGRAM_DOCS) == 3

    @pytest.mark.asyncio
    async def test_generate_pack(self, fresh_state, mock_ai):
        mock_ai.return_value = "# Generated Doc\nContent."
        docs = await generate_handoff_intelligence_pack(
            fresh_state, {"app_name": "TestApp"},
        )
        assert len(docs) >= 4
        assert "app_operations_manual" in docs