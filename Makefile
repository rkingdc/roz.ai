# Makefile for the assistant project

# Define variables
PYTHON = ~/.venv/assistant/bin/python
LOG_FILE = roz.ai.log
# Use single quotes for the pattern to avoid shell expansion issues within Make
PROCESS_PATTERN = '/home/roz/.venv/assistant/bin/python -m uvicorn.*run:asgi_app'
# Increase timeout to 120 seconds for potentially long AI operations
RUN_CMD = $(PYTHON) -m uvicorn run:asgi_app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120

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
	@$(RUN_CMD) 2>&1 | tee $(LOG_FILE) &

# Target to display help
.PHONY: help
help:
	@echo "----------------------------------------------------"
	@echo "Makefile for the AI Assistant Application"
	@echo "----------------------------------------------------"
	@echo "Available targets:"
	@echo "  make start   - Stops any existing process and starts the application using uvicorn."
	@echo "                 Logs output to $(LOG_FILE) and the console."
	@echo "  make stop    - Attempts to stop the running application process."
	@echo "  make test    - Runs the pytest test suite."
	@echo "  make help    - Displays this help message."
	@echo "----------------------------------------------------"

# Add other targets as needed (e.g., install, clean)
