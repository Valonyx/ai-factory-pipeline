# Architecture Decision Records — AI Factory Pipeline v5.6

Index of all ADRs referenced in the specification. ADRs document significant technical decisions with context, alternatives considered, and rationale.

---

## Core Architecture ADRs

| ADR | Title | Status | Spec Section |
|-----|-------|--------|-------------|
| ADR-001 | Polyglot stack support (6 stacks) | Accepted | §2.6 |
| ADR-002 | PipelineState as single mutable object | Accepted | §2.1 |
| ADR-003 | LangGraph for DAG orchestration | Accepted | §2.7.1 |
| ADR-004 | 4-role AI architecture (Scout/Strategist/Engineer/QF) | Accepted | §2.6, §3.8 |
| ADR-005 | Neo4j for Mother Memory (knowledge graph) | Accepted | §6.1 |
| ADR-006 | Supabase for relational state | Accepted | §5.6 |
| ADR-007 | Telegram as primary operator interface | Accepted | §5.1 |
| ADR-008 | KSA-first data residency (me-central1) | Accepted | §2.8 |
| ADR-009 | Budget Governor 4-tier model | Accepted | §2.14 |
| ADR-010 | War Room 3-level escalation | Accepted | §2.2.4 |
| ADR-015 | Stub-first development (production stubs) | Accepted | §2.6 |
| ADR-020 | User-space enforcement (no sudo) | Accepted | §2.5 |
| ADR-030 | Continuous Legal Thread (pre/post hooks) | Accepted | §2.7.3 |
| ADR-035 | Triple-write state persistence | Accepted | §6.7 |
| ADR-040 | Autopilot/Copilot autonomy modes | Accepted | §3.7 |
| ADR-006 | GCP Secret Manager for all credentials | Accepted | §2.11 |
| ADR-044 | Graduated Budget Degradation (4-tier) | Accepted | §2.14 |
| ADR-046 | Pre-deploy gate inside router | Accepted | §2.7.1 |
| ADR-049 | Scout context tier (small/medium/large) | Accepted | §2.6 |
| ADR-051 | Operator Handoff Intelligence Pack | Accepted | §4.9 |

## Audit-Derived ADRs

| ADR | Title | Fix | Spec Section |
|-----|-------|-----|-------------|
| ADR-043 | Runtime Model Override for Emergency Downgrade | FIX-03 | §2.6 |
| ADR-044 | Graduated Budget Degradation (4-tier) | FIX-05 | §2.14 |
| ADR-045 | Strict Compliance Enforcement with Operator Override | FIX-06 | §7.6 |
| ADR-046 | Pre-Deploy Operator Acknowledgment Gate | FIX-08 | §4.6 |
| ADR-047 | Version Hygiene Enforcement | FIX-16 | §8.11 |
| ADR-048 | Budget Buffer Segmentation | FIX-17 | §1.4 |
| ADR-049 | Scout Context-Tier Ceiling | FIX-19 | §3.1 |
| ADR-050 | Telegram-Native Operator Recovery | FIX-20 | §7.3 |
| ADR-051 | Operator Handoff Intelligence Pack | FIX-27 | §4.9 |

---

## FIX Index

Targeted fixes applied across specification versions:

| FIX | Title | Version | Spec Section |
|-----|-------|---------|-------------|
| FIX-03 | Model override chain | v5.4 | §2.6 |
| FIX-04 | Function Contract Reference table | v5.4 | §8.10 |
| FIX-05 | Budget Degradation Governor 4-tier | v5.5 | §2.14 |
| FIX-06 | Advisory vs Strict store compliance toggle | v5.5 | §7.6 |
| FIX-07 | Compliance Artifact Generator at S2 | v5.5 | §4.3.1 |
| FIX-13 | Vector search backend configuration | v5.5 | §6.7.1 |
| FIX-19 | Scout context tier limits | v5.6 | §2.6 |
| FIX-21 | iOS 5-step submission protocol | v5.6 | §4.7 |
| FIX-27 | Handoff Intelligence Pack (7 doc types) | v5.6 | §4.9, §8.10 |

---

## Decision Template

New ADRs follow this format:

ADR-NNN: Title
Status: Proposed | Accepted | Deprecated | Superseded Date: YYYY-MM-DD Spec Section: §X.Y

Context
What is the technical context and problem?

Decision
What did we decide and why?

Alternatives Considered
What other options were evaluated?

Consequences
What are the positive and negative outcomes?


---

## Notes

- ADR numbers are not sequential — gaps indicate internal-only decisions
- All ADRs are referenced in the v5.6 specification document with their number
- Superseded ADRs remain in the index with updated status
- New ADRs require explicit review before integration into the specification
