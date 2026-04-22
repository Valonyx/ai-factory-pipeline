# AI Factory Pipeline v5.8.15 — three-tier test targets (Issue 49)
#
# test-unit         fast, mocked, always runs
# test-integration  real free-tier providers + real filesystem; requires
#                   INTEGRATION_TEST_MODE=1 + a populated .env
# test-e2e          full pipeline via real CLI / Telegram harness; requires
#                   E2E_TEST_MODE=1

PYTEST ?= pytest

.PHONY: test test-unit test-integration test-e2e test-all test-collect

test: test-unit

test-unit:
	$(PYTEST) -m unit --tb=short

test-integration:
	INTEGRATION_TEST_MODE=1 $(PYTEST) -m integration --tb=short

test-e2e:
	E2E_TEST_MODE=1 $(PYTEST) -m e2e --tb=short

test-all: test-unit
	INTEGRATION_TEST_MODE=1 E2E_TEST_MODE=1 $(PYTEST) --tb=short

test-collect:
	$(PYTEST) --collect-only -q
