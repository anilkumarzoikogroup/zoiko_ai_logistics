.PHONY: install lint test test-vectors ci

install:
	pip install -e "packages/zoiko-common[dev]"

lint:
	ruff check .

test:
	pytest packages/zoiko-common/tests -v --cov=zoiko_common --cov-report=term-missing --cov-fail-under=80

test-vectors:
	pytest packages/zoiko-common/tests -v -m "jcs_vector or merkle_vector" --tb=short

ci: lint test-vectors test
