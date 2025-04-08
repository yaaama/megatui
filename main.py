#!/usr/bin/env python

import asyncio

import megatui.mega.megacmd as megacmd

# Import the App class from the ui module
from megatui.app import MegaAppTUI


# TODO Add some logging
# import logging
#
# logging.basicConfig(
#     level="INFO", # Adjust level (DEBUG, INFO, WARNING, ERROR)
#     handlers=[
#         logging.FileHandler("mega_tui.log"), # Log to a file
#         # logging.StreamHandler()
#     ]
# )


async def main() -> None:
    """Main entry point."""
    # Check login status before starting TUI (optional but good practice)
    logged_in, message = await megacmd.check_mega_login()
    if not logged_in:
        print(f"MEGA Login Check: {message}")
        return

    print(f"Logged in! {message}")  # Or just proceed

    # Start the TUI
    app = MegaAppTUI()
    await app.run_async()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
