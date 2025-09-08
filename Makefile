# Makefile to create venv and manage dev environment

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

.PHONY: help venv install upgrade dev run shell clean

help:
	@printf "Targets:\n  venv    Create virtualenv\n  install Install requirements\n  upgrade Upgrade installed requirements\n  dev     Run uvicorn dev server (port 8080)\n  shell   Open shell with venv activated\n  lint    Run ruff/flake8 (if installed)\n  format  Run black/isort (if installed)\n  test    Run pytest (if installed)\n  clean   Remove venv & caches\n"

venv:
	@echo "Creating virtual environment $(VENV) if missing..."
	@if [ ! -d "$(VENV)" ]; then python3 -m venv $(VENV); fi
	@$(PY) -m pip install --upgrade pip setuptools wheel

install: venv
	@if [ -f requirements.txt ]; then $(PIP) install -r requirements.txt; else echo "requirements.txt not found; skipping"; fi

upgrade: venv
	@if [ -f requirements.txt ]; then $(PIP) install -U -r requirements.txt; else echo "requirements.txt not found; skipping"; fi

dev: install
	@echo "Starting dev server on http://127.0.0.1:8080"
	@$(UVICORN) main:app --reload --port 8080

run: dev

shell: venv
	@echo "Launching shell with venv activated"
	@bash -c "source $(VENV)/bin/activate && exec $$SHELL"

clean:
	@echo "Removing venv and caches"
	@rm -rf $(VENV) .pytest_cache build dist
	@find . -type d -name "__pycache__" -exec rm -rf {} + || true
