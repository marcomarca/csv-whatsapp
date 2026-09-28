"""Unified Entry Point for WhatsApp Backup to CSV.

Launches the Desktop GUI by default, or runs the CLI tool when arguments/commands are supplied.
"""

import sys


def main() -> None:
    cli_keywords = {
        "accounts",
        "export",
        "status",
        "devices",
        "key",
        "capture-key",
        "history",
        "parse-local",
        "--help",
        "-h",
        "-v",
        "--verbose",
        "--cli",
    }

    # If any CLI argument or keyword is provided in sys.argv, run the CLI
    has_cli_args = len(sys.argv) > 1 and any(arg in cli_keywords for arg in sys.argv[1:])

    if has_cli_args:
        # Remove '--cli' flag if passed explicitly
        if "--cli" in sys.argv:
            sys.argv.remove("--cli")
        from src.cli import main as cli_main

        cli_main()
    else:
        from src.app import main as gui_main

        gui_main()


if __name__ == "__main__":
    main()
