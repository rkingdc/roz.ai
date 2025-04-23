# Makefile for the assistant project

# Define variables
VENV_DIR = ~/.venv/assistant
PYTHON = $(VENV_DIR)/bin/python
LOG_FILE = roz.ai.log

DEV_DB_PATH = /tmp/assistant_dev_db.sqlite # Define temporary dev database path
# Increase timeout to 120 seconds for potentially long AI operations
GUNICORN_CMD = $(PYTHON) -m gunicorn --workers 1 --bind 0.0.0.0:8000 --timeout 360 run:app

# Default target (optional)
.PHONY: default
default: help

# Target to set up the virtual environment and install dependencies
.PHONY: install
install:
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
start: stop install
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
	# Start flask run with the temporary database name, TEST_DATABASE flag, IS_DEV_SERVER flag, and --debug flag
	@DATABASE_NAME=$(DEV_DB_PATH) TEST_DATABASE=TRUE IS_DEV_SERVER=TRUE $(PYTHON) -m flask --app run run --debug --port 5000


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
  @echo "  make start-dev - Start the application in development mode using 'flask run --debug' (stop with Ctrl+C)"
	@echo "  make test    - Runs the pytest test suite. Runs 'install' first."
	@echo "  make help    - Displays this help message."
	@echo "----------------------------------------------------"


# Add other targets as needed (e.g., clean)
