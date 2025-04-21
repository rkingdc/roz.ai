# Makefile for the assistant project

# Define variables
VENV_DIR = ~/.venv/assistant
PYTHON = $(VENV_DIR)/bin/python
LOG_FILE = roz.ai.log
# Use single quotes for the pattern to avoid shell expansion issues within Make
# Updated PROCESS_PATTERN to use VENV_DIR
PROCESS_PATTERN = '$(VENV_DIR)/bin/python -m uvicorn.*run:asgi_app'
# Increase timeout to 120 seconds for potentially long AI operations
RUN_CMD = $(PYTHON) -m uvicorn run:asgi_app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120

# Default target (optional)
.PHONY: default
default: help

# Target to set up the virtual environment and install dependencies
.PHONY: install
install:
	@echo "Setting up virtual environment and installing dependencies..."
	@mkdir -p $(VENV_DIR) # Ensure parent directories exist
	@test -d $(VENV_DIR)/bin/activate || (echo "Creating virtual environment at $(VENV_DIR)..." && python3 -m venv $(VENV_DIR))
	@echo "Upgrading pip and installing dependencies..."
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install -r requirements.txt
	@echo "Checking for .env file..."
	@test -f .env || cp .env.example .env
	@test -f .env && echo ".env file exists." || echo ".env file created from .env.example. Please configure it."
	@echo "Installation complete."

# Target to run tests
.PHONY: test
test: install
	@echo "Running tests..."
	$(PYTHON) -m pytest

# Target to stop the application
.PHONY: stop
stop:
	@echo "Stopping application..."
	@-pkill -f $(PROCESS_PATTERN) || echo "Ignoring pkill exit status. Check manually if process persists."

# Target to start the application
.PHONY: start
start: stop install
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
	@echo "  make install - Creates a virtual environment at $(VENV_DIR) (if it doesn't exist),"
	@echo "                 installs dependencies from requirements.txt, and creates a .env file"
	@echo "                 from .env.example if it doesn't exist."
	@echo "  make start   - Stops any existing process and starts the application using uvicorn."
	@echo "                 Logs output to $(LOG_FILE) and the console. Runs 'install' first."
	@echo "  make stop    - Attempts to stop the running application process based on the virtual environment path."
	@echo "  make test    - Runs the pytest test suite. Runs 'install' first."
	@echo "  make help    - Displays this help message."
	@echo "----------------------------------------------------"

# Add other targets as needed (e.g., clean)
