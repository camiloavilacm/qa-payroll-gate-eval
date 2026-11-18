PYTHON ?= python
check:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy --strict src tests
	PAYROLL_GATE_OFFLINE=1 $(PYTHON) -m pytest -q --disable-socket
