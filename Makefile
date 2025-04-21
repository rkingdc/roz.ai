# Makefile for the assistant project

# Define variables
PYTHON = ~/.venv/assistant/bin/python
LOG_FILE = roz.ai.log
DEV_DB_PATH = /tmp/assistant_dev_db.sqlite # Define temporary dev database path
# Increase timeout to 120 seconds for potentially long AI operations
GUNICORN_CMD = $(PYTHON) -m gunicorn --workers 1 --bind 0.0.0.0:8000 --timeout 360 run:app

# Default target (optional)
.PHONY: default
default: help

# Target to run tests
.PHONY: test
test:
	@echo "Running tests..."
	$(PYTHON) -m pytest

# Target to stop the application (specifically the gunicorn process from 'make start')
.PHONY: stop
stop:
	@echo "Stopping application..."
	@-ps -aux | grep [a]ssistant | grep python | grep gunicorn  | awk '{print $2}' | xargs kill -2  2> /dev/null
	# Add cleanup for the temporary dev database file (useful if 'start-dev' was interrupted)
	@echo "Cleaning up temporary dev database file..."
	@rm -f $(DEV_DB_PATH)

# Target to start the application (using gunicorn)
.PHONY: start
start: stop
	@echo "Starting application..."
	@sleep 1 # Give a moment for the old process to terminate
	@echo "Logging to $(LOG_FILE) and stdout."
	@$(GUNICORN_CMD) 2>&1 | tee $(LOG_FILE)

# Target to start the application in development mode with a temporary file database using flask run
.PHONY: start-dev
start-dev:
	@echo "Starting application in development mode with temporary file database on port 5000 using 'flask run --debug'..."
	# Clean up previous temporary file database
	@echo "Cleaning up previous temporary dev database file..."
	@rm -f $(DEV_DB_PATH)
	# Initialize the temporary database file
	@echo "Initializing database..."
	@DATABASE_NAME=$(DEV_DB_PATH) $(PYTHON) -m flask --app run init-db
	@echo "Starting Flask development server..."
	# Start flask run with the temporary database name and TEST_DATABASE flag
	@DATABASE_NAME=$(DEV_DB_PATH) TEST_DATABASE=TRUE $(PYTHON) -m flask --app run run --debug --port 5000

# Target to display help
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make start   - Start the application using gunicorn (stop with make stop)"
	@echo "  make stop    - Stop the gunicorn application process"
	@echo "  make start-dev - Start the application in development mode using 'flask run --debug' (stop with Ctrl+C)"
	@echo "  make test    - Run unit tests"
	@echo "  make help    - Show this help message"

# Add other targets as needed (e.g., install, clean)
