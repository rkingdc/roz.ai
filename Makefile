# Makefile for the assistant project

# Define variables
PYTHON := $(VENV_DIR)/bin/python
PIP := $(PYTHON) -m pip
VENV_DIR := .venv
RUN_FILE := run.py
SCHEMA_FILE := app/schema.sql
REQUIREMENTS_FILE := requirements.txt
TEST_DIR := tests
LINT_DIR := app tests
# Use a timestamp for the release directory name
RELEASE_DIR := releases/$(shell date +%Y%m%d-%H%M%S)
# Find the latest release directory, suppressing errors if 'releases' doesn't exist
LATEST_RELEASE := $(shell ls -td releases/*/ 2>/dev/null | head -n 1)

# Define the gunicorn command using the venv python
# Increase timeout to 120 seconds for potentially long AI operations
GUNICORN_CMD = $(PYTHON) -m gunicorn --workers 1 --bind 0.0.0.0:8000 --timeout 120 run:app

.PHONY: all venv install init-db run start test lint deploy clean help stop start-dev

all: install

venv:
	@echo "Creating virtual environment..."
	@test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	@echo "Virtual environment ready."

install: venv
	@echo "Installing dependencies..."
	@$(PIP) install -r $(REQUIREMENTS_FILE)
	@echo "Dependencies installed."

init-db: install
	@echo "Initializing the database..."
	@$(PYTHON) -m flask --app $(RUN_FILE) init-db
	@echo "Database initialized."

run: install init-db
	@echo "Starting the development server..."
	# Use flask run with the default database name (flaskr.sqlite in instance/)
	@$(PYTHON) -m flask --app $(RUN_FILE) run --debug --port 5000

# Modified start target to run from the latest release bundle
start:
	@if [ -z "$(LATEST_RELEASE)" ]; then \
		echo "Error: No releases found in the 'releases/' directory."; \
		echo "Run 'make deploy' first to create a release bundle."; \
		exit 1; \
	fi; \
	echo "Starting latest release: $(LATEST_RELEASE)"; \
	# Change directory to the latest release and run the app using the venv python
	@cd $(LATEST_RELEASE) && $(PYTHON) $(RUN_FILE)

test: install
	@echo "Running tests..."
	@$(PYTHON) -m pytest $(TEST_DIR)

lint: install
	@echo "Running linting..."
	@$(PIP) install flake8 isort black > /dev/null # Ensure linters are installed silently
	@$(VENV_DIR)/bin/flake8 $(LINT_DIR)
	@$(VENV_DIR)/bin/isort --check-only $(LINT_DIR)
	@$(VENV_DIR)/bin/black --check $(LINT_DIR)

# New deploy target
deploy: install
	@echo "Creating release bundle in $(RELEASE_DIR)..."
	@mkdir -p $(RELEASE_DIR)/app
	# Copy necessary files and directories
	@cp -r app/* $(RELEASE_DIR)/app/ # Copy contents of app/
	@cp $(RUN_FILE) $(RELEASE_DIR)/
	@cp $(REQUIREMENTS_FILE) $(RELEASE_DIR)/
	@cp .env.example $(RELEASE_DIR)/
	# schema.sql is already inside app/, copied by the recursive cp above
	@echo "Release bundle created successfully."
	@echo "Run 'make start' to run the latest release."

# Target to stop the application (specifically the gunicorn process from 'make start')
# Note: This will only stop the gunicorn process started by 'make start'.
# It will NOT stop the 'flask run' process started by 'make run' or 'make start-dev'.
stop:
	@echo "Attempting to stop gunicorn process..."
	@-pkill -f "gunicorn --workers 1 --bind 0.0.0.0:8000" 2>/dev/null || echo "No gunicorn process found."
	# Add cleanup for the temporary dev database file (useful if 'start-dev' was interrupted)
	@echo "Cleaning up temporary dev database file..."
	@rm -f /tmp/assistant_dev_db.sqlite # Hardcoded path from start-dev target

# Target to start the application in development mode with a temporary file database using flask run
start-dev:
	@echo "Starting application in development mode with temporary file database on port 5000 using 'flask run --debug'..."
	# Clean up previous temporary dev database file
	@echo "Cleaning up previous temporary dev database file..."
	@rm -f /tmp/assistant_dev_db.sqlite
	# Initialize the temporary database file
	@echo "Initializing database..."
	@DATABASE_NAME=/tmp/assistant_dev_db.sqlite $(PYTHON) -m flask --app $(RUN_FILE) init-db
	@echo "Starting Flask development server..."
	# Start flask run with the temporary database name, TEST_DATABASE flag, IS_DEV_SERVER flag, and --debug flag
	@DATABASE_NAME=/tmp/assistant_dev_db.sqlite TEST_DATABASE=TRUE IS_DEV_SERVER=TRUE $(PYTHON) -m flask --app $(RUN_FILE) run --debug --port 5000


# Target to display help
help:
	@echo "Available targets:"
	@echo "  make install   - Create venv and install dependencies"
	@echo "  make init-db   - Initialize the database (requires install)"
	@echo "  make run       - Start the development server using 'flask run --debug' (requires install, init-db)"
	@echo "  make start     - Start the application using gunicorn from the latest release bundle (requires install, deploy)"
	@echo "  make stop      - Stop the gunicorn application process started by 'make start'"
	@echo "  make start-dev - Start the application in development mode with a temporary database (stop with Ctrl+C)"
	@echo "  make test      - Run unit tests (requires install)"
	@echo "  make lint      - Run linting checks (requires install)"
	@echo "  make deploy    - Create a versioned release bundle in the 'releases/' directory (requires install)"
	@echo "  make clean     - Remove virtual environment, cache files, and default dev db"
	@echo "  make help      - Show this help message"

