"""Entry point: ``python -m clipmgr``."""

import sys


def main() -> None:
    if sys.platform != "darwin":
        sys.exit("clipmgr runs on macOS only.")
    from .macos.app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
