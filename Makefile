# Makefile for the assistant project

# Define the python interpreter from the virtual environment
# Adjust the path if your venv is located elsewhere
PYTHON = ~/.venv/assistant/bin/python

# Default target (optional)
.PHONY: default
default: help

# Target to run tests
.PHONY: test
test:
	@echo "Running tests..."
	$(PYTHON) -m pytest

# Target to display help (optional)
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make test    - Run unit tests"
	@echo "  make help    - Show this help message"

# Add other targets as needed (e.g., install, clean, run)
