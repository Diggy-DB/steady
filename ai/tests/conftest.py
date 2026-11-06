"""Shared test setup."""

import os

# Tests never start the real long-term memory (it would call the model and write ai/memory/).
# This runs before any test imports ai.server.
os.environ["MEMORY"] = "off"
