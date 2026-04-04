"""Tests for factory.legal (P7 Legal Engine)."""

import pytest
from factory.legal.regulatory import (
    resolve_regulatory_body, REGULATORY_BODY_MAPPING,
    get_regulators_for_category, CATEGORY_REGULATORS,
    PDPL_REQUIREMENTS, ALLOWED_DATA_REGIONS, PRIMARY_DATA_REGION,
    is_ksa_compliant_region, is_within_deploy_window,
    check_prohibited_sdks, PROHIBITED_SDKS,
)
from factory.legal.checks import (
    LEGAL_CHECKS_BY_STAGE, legal_check_hook,
    get_checks_for_stage, get_all_check_names, run_legal_check,
)
from factory.legal.docugen import (
    DOCUGEN_TEMPLATES, generate_legal_documents,
    get_required_docs, get_missing_docs,
)
from factory.legal.compliance_gate import (
    ComplianceGateResult, run_store_preflight, record_store_event,
)


class TestRegulatory:
    def test_citc_resolves_to_cst(self):
        assert resolve_regulatory_body("CITC") == "CST"

    def test_sama_aliases(self):
        assert resolve_regulatory_body("SAMA") == "SAMA"
        assert resolve_regulatory_body("Saudi Central Bank") == "SAMA"

    def test_all_14_aliases(self):
        assert len(REGULATORY_BODY_MAPPING) >= 14

    def test_category_regulators(self):
        regs = get_regulators_for_category("finance")
        assert "SAMA" in regs

    def test_unknown_category(self):
        regs = get_regulators_for_category("unknown_xyz")
        assert isinstance(regs, list)


class TestDataResidency:
    def test_primary_region(self):
        assert PRIMARY_DATA_REGION == "me-central1"

    def test_allowed_regions(self):
        assert len(ALLOWED_DATA_REGIONS) == 4
        assert is_ksa_compliant_region("me-central1") is True
        assert is_ksa_compliant_region("us-east1") is False


class TestDeployWindow:
    def test_within_window(self):
        assert is_within_deploy_window(10) is True
        assert is_within_deploy_window(6) is True
        assert is_within_deploy_window(22) is True

    def test_outside_window(self):
        assert is_within_deploy_window(3) is False
        assert is_within_deploy_window(23) is False


class TestProhibitedSDKs:
    def test_clean_deps(self):
        result = check_prohibited_sdks(["firebase-auth", "stripe-sdk"])
        assert len(result) == 0

    def test_detected_sdks(self):
        result = check_prohibited_sdks(["huawei-analytics", "firebase"])
        assert "huawei-analytics" in result


class TestPDPL:
    def test_pdpl_requirements(self):
        assert PDPL_REQUIREMENTS["consent_required"] is True
        assert PDPL_REQUIREMENTS["data_residency"] == "KSA"
        assert PDPL_REQUIREMENTS["breach_notification_hours"] == 72
        assert len(PDPL_REQUIREMENTS["subject_rights"]) == 6


class TestLegalChecks:
    def test_checks_by_stage(self):
        assert len(LEGAL_CHECKS_BY_STAGE) >= 5

    def test_all_checks_registered(self):
        names = get_all_check_names()
        assert len(names) == 9

    @pytest.mark.asyncio
    async def test_data_residency_check(self, fresh_state, mock_ai):
        fresh_state.project_metadata["deploy_region"] = "me-central1"
        result = await run_legal_check(fresh_state, "data_residency_compliance")
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_prohibited_sdk_check(self, fresh_state, mock_ai):
        fresh_state.project_metadata["dependencies"] = ["firebase"]
        result = await run_legal_check(fresh_state, "no_prohibited_sdks")
        assert result["passed"] is True


class TestDocuGen:
    def test_templates(self):
        assert len(DOCUGEN_TEMPLATES) == 5
        assert "privacy_policy" in DOCUGEN_TEMPLATES
        assert "terms_of_use" in DOCUGEN_TEMPLATES

    def test_required_docs(self):
        docs = get_required_docs("e-commerce")
        assert "privacy_policy" in docs
        assert "terms_of_use" in docs

    @pytest.mark.asyncio
    async def test_generate(self, fresh_state, mock_ai):
        mock_ai.return_value = "# Generated Document\nContent here."
        await generate_legal_documents(fresh_state, {
            "business_model": "e-commerce",
            "app_name": "TestApp",
        })
        assert len(fresh_state.legal_documents) >= 2


class TestComplianceGate:
    @pytest.mark.asyncio
    async def test_store_preflight(self, fresh_state, mock_ai):
        mock_ai.return_value = '{"blockers": [], "warnings": [], "guidelines_version": "2025", "confidence": 0.8}'
        results = await run_store_preflight(
            fresh_state,
            {"features": ["camera", "payments"], "category": "e-commerce"},
            ["ios", "android"],
        )
        assert len(results) == 2