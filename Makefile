# Makefile for the assistant project

# Define variables
# Define the path to the Python executable *inside* the virtual environment

VENV_DIR := /home/roz/.venv/assistant
PYTHON := $(VENV_DIR)/bin/python3 # Changed to python3
PIP := $(VENV_DIR)/bin/pip3 # Changed to pip3
RUN_FILE := run.py
# SCHEMA_FILE := app/schema.sql # No longer needed, schema managed by migrations
REQUIREMENTS_FILE := requirements.txt
PROD_DB := assistant_chat_v10.db
TEST_DIR := tests
LINT_DIR := app tests
# Use a timestamp for the release directory name
RELEASE_DIR := releases/$(shell date +%Y%m%d-%H%M%S)
# Find the latest release directory, suppressing errors if 'releases' doesn't exist
LATEST_RELEASE := $(shell ls -td releases/*/ 2>/dev/null | head -n 1)

# Define the gunicorn command using the venv python
# Increase timeout to 120 seconds for potentially long AI operations
# Use run:app which should contain the app instance created by create_app()
GUNICORN_CMD = $(PYTHON) flask --workers 1 --bind 0.0.0.0:8000 --timeout 120 run:app

# Add migration commands and auth check to PHONY
.PHONY: all venv install init-db upgrade migrate revision run start auth test lint deploy clean help stop start-dev check-gcloud-auth

all: install

venv:
	@echo "Creating virtual environment..."
	# Use the system's python3 command to create the venv
	@test -d $(VENV_DIR) || python3 -m venv $(VENV_DIR)
	@echo "Virtual environment ready."

install: venv
	@echo "Installing dependencies..."
	@$(PIP) install -r $(REQUIREMENTS_FILE) # Now uses $(PIP) which is .venv/bin/pip3
	@echo "Dependencies installed."

# init-db is replaced by 'upgrade'
# init-db: install
#	@echo "Initializing the database..."
#	@$(PYTHON) -m flask --app $(RUN_FILE) init-db # Now uses .venv/bin/python3
#	@echo "Database initialized."

# New migration targets
# Note: 'flask db init' needs to be run manually ONCE to create the migrations folder
upgrade: install
	@echo "Applying database migrations..."
	@$(PYTHON) -m flask --app $(RUN_FILE) db upgrade
	@echo "Database is up-to-date."

auth:
	@gcloud auth application-default login

# Target to generate a new migration script after model changes
# Usage: make revision msg="Your description"
revision: install
	@echo "Generating new migration revision..."
	@$(PYTHON) -m flask --app $(RUN_FILE) db migrate -m "$(msg)"
	@echo "New revision generated. Review it in the 'migrations/versions' directory."

# Target to generate a new migration script (alias for revision)
migrate: revision

# run: install upgrade # Depends on upgrade now
#	@echo "Starting the development server..."
#	# Use flask run with the default database name (flaskr.sqlite in instance/)
#	@$(PYTHON) -m flask --app $(RUN_FILE) run --debug --port 5000 # Now uses .venv/bin/python3
# Note: 'make run' is removed in favor of 'make start-dev' which uses uvicorn

# Modified start target to run migrations and check auth first
start: upgrade check-gcloud-auth # Depends on upgrade and check-gcloud-auth now
	@if [ -z "$(LATEST_RELEASE)" ]; then \
		echo "Error: No releases found in the 'releases/' directory."; \
		echo "Run 'make deploy' first to create a release bundle."; \
		exit 1; \
	fi; \
	echo "Starting latest release: $(LATEST_RELEASE)"; \
	# Change directory to the latest release and run the app using the venv python
	@cd $(LATEST_RELEASE) && DATABASE_NAME="../../$(PROD_DB)" flask --app $(RUN_FILE) run --port 8000

launch:
	firefox --new-tab localhost:8000 > /dev/null 

test: install check-gcloud-auth # Depends on check-gcloud-auth now (if tests hit live APIs)
	@echo "Running tests..."
	# Note: If your tests mock Google Cloud APIs, you might remove the check-gcloud-auth dependency here.
	@$(PYTHON) -m pytest $(TEST_DIR) # Now uses .venv/bin/python3

lint: install
	@echo "Running linting..."
	@$(PIP) install flake8 isort black > /dev/null # Ensure linters are installed silently
	@$(VENV_DIR)/bin/flake8 $(LINT_DIR) # This was already explicit, but let's keep it consistent
	@$(VENV_DIR)/bin/isort --check-only $(LINT_DIR) # This was already explicit
	@$(VENV_DIR)/bin/black --check $(LINT_DIR) # This was already explicit

# New deploy target
deploy: install
	@echo "Creating release bundle in $(RELEASE_DIR)..."
	@mkdir -p $(RELEASE_DIR)/app
	# Copy necessary files and directories
	@cp -r app/* $(RELEASE_DIR)/app/ # Copy contents of app/
	@cp $(RUN_FILE) $(RELEASE_DIR)/
	@cp $(REQUIREMENTS_FILE) $(RELEASE_DIR)/
	@cp .env.example $(RELEASE_DIR)/
	# schema.sql is no longer needed or copied
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

# Target to start the application in development mode with a temporary file database using Flask's dev server
start-dev: install check-gcloud-auth # Depends on install and check-gcloud-auth now
	@echo "Starting application in development mode with temporary file database using Flask's dev server..."
	# Auth check is now done via dependency
	# Clean up previous temporary dev database file if it exists
	@echo "Cleaning up temporary dev database file..."
	@rm -f /tmp/assistant_dev_db.sqlite
	# Now apply migrations to the clean database file
	@echo "Applying database migrations to the temporary database..."
	@DATABASE_NAME=/tmp/assistant_dev_db.sqlite TEST_DATABASE=TRUE IS_DEV_SERVER=TRUE $(PYTHON) -m flask --app $(RUN_FILE) db upgrade
	@echo "Database migrations applied."
	# Start Flask development server...
	@echo "Starting Flask development server..."
	# Start flask run with debug mode and set environment variables
	@DATABASE_NAME=/tmp/assistant_dev_db.sqlite TEST_DATABASE=TRUE IS_DEV_SERVER=TRUE $(PYTHON) -m flask --app $(RUN_FILE) run --debug --port 5000


# Target to check for Google Cloud Application Default Credentials
check-gcloud-auth:
	@echo "Checking for Google Cloud credentials..."
	@if [ -z "$$GOOGLE_APPLICATION_CREDENTIALS" ] && [ ! -f "$$HOME/.config/gcloud/application_default_credentials.json" ]; then \
		echo ""; \
		echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"; \
		echo "ERROR: Google Cloud Application Default Credentials not found."; \
		echo "Please configure authentication using ONE of the following methods:"; \
		echo "  1. Set the GOOGLE_APPLICATION_CREDENTIALS environment variable:"; \
		echo "     export GOOGLE_APPLICATION_CREDENTIALS=\"/path/to/your/service-account-key.json\""; \
		echo "  2. Log in using gcloud CLI (if GOOGLE_APPLICATION_CREDENTIALS is not set):"; \
		echo "     gcloud auth application-default login"; \
		echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"; \
		echo ""; \
		exit 1; \
	else \
		echo "Google Cloud credentials found (either GOOGLE_APPLICATION_CREDENTIALS or gcloud ADC file)."; \
	fi

# Target to display help
help:
	@echo "Available targets:"
	@echo "  make install   - Create venv and install dependencies"
	@echo "  make upgrade   - Apply database migrations (creates DB if needed)"
	@echo "  make revision msg=\"<msg>\" - Generate a new database migration script"
	@echo "  make migrate msg=\"<msg>\"  - Alias for 'make revision'"
	# @echo "  make run       - (Removed, use start-dev)"
	@echo "  make start     - Apply migrations and start gunicorn from the latest release bundle"
	@echo "  make stop      - Stop the gunicorn application process started by 'make start'"
	@echo "  make start-dev - Apply migrations and start the Flask dev server with a temporary DB"
	@echo "  make test      - Run unit tests (requires install)"
	@echo "  make lint      - Run linting checks (requires install)"
	@echo "  make deploy    - Create a versioned release bundle in the 'releases/' directory"
	@echo "  make clean     - Remove venv, cache files, default dev db, and temp dev db"
	@echo "  make help      - Show this help message"

# Update clean target to remove migrations folder and temp dev db
clean:
	@echo "Cleaning up..."
	@rm -rf $(VENV_DIR)
	@rm -f $(PROD_DB) # Remove default prod db file if it exists
	@rm -f /tmp/assistant_dev_db.sqlite # Remove temp dev db file
	@rm -rf instance/ # Remove instance folder which might contain dev db (e.g. flask.sqlite)
	# Removed: @rm -rf migrations/ # Remove migrations folder
	@find . -type f -name '*.pyc' -delete
	@find . -type d -name '__pycache__' -delete
	@echo "Clean complete."
