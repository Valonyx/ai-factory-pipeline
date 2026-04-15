"""
AI Factory Pipeline v5.8 — Legal Engine Module

Continuous legal thread, DocuGen, regulatory resolution, store compliance.
"""

from factory.legal.regulatory import (
    REGULATORY_BODY_MAPPING,
    resolve_regulatory_body,
    get_regulators_for_category,
    CATEGORY_REGULATORS,
    PDPL_REQUIREMENTS,
    ALLOWED_DATA_REGIONS,
    PRIMARY_DATA_REGION,
    is_ksa_compliant_region,
    is_within_deploy_window,
    check_prohibited_sdks,
    PROHIBITED_SDKS,
)

from factory.legal.checks import (
    LEGAL_CHECKS_BY_STAGE,
    legal_check_hook,
    run_legal_check,
    get_checks_for_stage,
    get_all_check_names,
)

from factory.legal.docugen import (
    DOCUGEN_TEMPLATES,
    LEGAL_DISCLAIMER,
    generate_legal_documents,
    get_required_docs,
    get_missing_docs,
    is_doc_generated,
)

from factory.legal.compliance_gate import (
    ComplianceGateResult,
    STRICT_STORE_COMPLIANCE,
    run_store_preflight,
    record_store_event,
)

__all__ = [
    # Regulatory
    "REGULATORY_BODY_MAPPING", "resolve_regulatory_body",
    "get_regulators_for_category", "PDPL_REQUIREMENTS",
    "is_ksa_compliant_region", "check_prohibited_sdks",
    # Legal Checks
    "LEGAL_CHECKS_BY_STAGE", "legal_check_hook",
    "run_legal_check", "get_checks_for_stage", "get_all_check_names",
    # DocuGen
    "DOCUGEN_TEMPLATES", "generate_legal_documents",
    "get_required_docs", "get_missing_docs",
    # Compliance Gate
    "ComplianceGateResult", "STRICT_STORE_COMPLIANCE",
    "run_store_preflight", "record_store_event",
]