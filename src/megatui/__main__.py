"""Main entry-point for our application."""

import asyncio

from megatui.app import run_app

if __name__ == "__main__":
    asyncio.run(run_app())
