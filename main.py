import asyncio
import sys

from megatui.app import MegaAppTUI  # Import the main App class
from megatui.mega.megacmd import check_mega_login  # Import login check

async def run_app() -> None:
    """Checks login and runs the Textual app."""
    # Check login status before starting TUI
    print("Checking MEGA login status...")
    logged_in, message = await check_mega_login()

    if not logged_in:
        print(f"MEGA Login Check Failed: {message}", file=sys.stderr)
        print(
            "Please log in using 'mega-login' or check 'mega-whoami'.", file=sys.stderr
        )
        return  # Exit if not logged in

    print(f"MEGA Login Check: OK ({message})")  # Show username on success

    # Start the TUI
    app = MegaAppTUI()
    await app.run_async()

if __name__ == "__main__":
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        print("\nExiting MegaTUI...")
    except Exception as e:
        # Log unexpected errors more gracefully
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        # Consider adding more detailed logging or traceback here if needed for debugging
        # import traceback
        # traceback.print_exc()
        sys.exit(1)  # Exit with an error code
