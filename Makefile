##
# megatui
#
# @file

# ==============================================================================
# Configuration
# ==============================================================================

# The path to your main application file
APP_PATH := src/megatui/app.py

# The name for the HTML profiling report
PROFILE_HTML_FILE := etc/profile.html
# Folder of source files
SOURCE_FOLDER := src/megatui

ARGS :=

.PHONY: help install run con conxe profile clean upgrade fmt

# The default command when you just type `make`.
default: help

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@echo "  install        Sync dependencies using 'uv sync'."
	@echo "  run            Run the application using 'textual run --dev'."
	@echo "  con 	        	Run 'textual console'. Pass arguments via the ARGS variable."
	@echo "                 Example: make console ARGS=\"src/megatui/app.py MegatuiApp\""
	@echo "  conxe 	        Run 'textual console -x event'. Pass arguments via the ARGS variable."
	@echo "  profile 				Profile the app and generate an interactive HTML report."
	@echo "  clean          Remove generated files (e.g., profile reports, __pycache__)."
	@echo "  upgrade        Upgrade uv packages and pre-commit hooks."
	@echo "  lint        		Format all source files with ruff and fix them."

lint:
	@echo "--> Fixing with ruff"
	ruff check --fix $(SOURCE_FOLDER)
	@echo "--> Formatting with ruff"
	ruff format $(SOURCE_FOLDER)

upgrade:
	@echo "--> Upgrading packages with uv..."
	uv sync
	@echo "--> Upgrading pre-commit hooks..."
	pre-commit autoupdate

# Install/sync dependencies from your pyproject.toml
install:
	@echo "--> Syncing dependencies with uv..."
	uv sync

# Run the application in development mode
run:
	@echo "--> Running the application..."
	uv run --dev textual run --dev $(APP_PATH)

# Run the Textual REPL/console with additional arguments
con:
	@echo "--> Running 'textual console' with arguments: $(ARGS)"
	@uv run --dev textual console $(ARGS)


conxe:
	@echo "--> Running 'textual console -x event'"
	@uv run --dev textual console -x event

# Profile the application and show the output in profile.html
profile:
	@echo "--> Generating HTML profile report at $(PROFILE_HTML_FILE)..."
	uv run --dev pyinstrument -r html -o $(PROFILE_HTML_FILE) $(APP_PATH)
	@echo "--> Profiling complete. You can now open $(PROFILE_HTML_FILE) in a browser."

# Clean up generated artifacts
clean:
	@echo "--> Cleaning up project..."
	@rm -f $(PROFILE_HTML_FILE)
	@uv clean
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "--> Cleanup complete."


# end
