import asyncio
import sys

from megatui.app import MegaAppTUI
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
        # Exit if not logged in
        return

    print(f"MEGA Login Check: OK ({message})")  # Show username on success

    # Start the TUI
    app = MegaAppTUI()

    await app.run_async(mouse=False)


if __name__ == "__main__":
    try:
        asyncio.run(run_app(), debug=True)
    except KeyboardInterrupt:
        print("\nExiting MegaTUI...")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        # Exit with an error code
        sys.exit(1)
