# Makefile for the assistant project

# Define variables
PYTHON = ~/.venv/assistant/bin/python
LOG_FILE = roz.ai.log
# Use single quotes for the pattern to avoid shell expansion issues within Make
PROCESS_PATTERN = '/home/roz/.venv/assistant/bin/python -m gunicorn.*run:app'
# Increase timeout to 120 seconds for potentially long AI operations
GUNICORN_CMD = $(PYTHON) -m gunicorn --workers 3 --bind 0.0.0.0:8000 --timeout 120 run:app

# Default target (optional)
.PHONY: default
default: help

# Target to run tests
.PHONY: test
test:
	@echo "Running tests..."
	$(PYTHON) -m pytest

# Target to display help (optional)
# Target to stop the application
.PHONY: stop
stop:
	@echo "Stopping application..."
	@-pkill -f $(PROCESS_PATTERN) || echo "Ignoring pkill exit status. Check manually if process persists."

# Target to start the application
.PHONY: start
start: stop
	@echo "Starting application..."
	@sleep 1 # Give a moment for the old process to terminate
	@echo "Logging to $(LOG_FILE) and stdout."
	@$(GUNICORN_CMD) 2>&1 | tee $(LOG_FILE) &

# Target to display help
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make start   - Start the application"
	@echo "  make stop    - Stop the application"
	@echo "  make test    - Run unit tests"
	@echo "  make help    - Show this help message"

# Add other targets as needed (e.g., install, clean)
