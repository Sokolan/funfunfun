"""PyInstaller entry point. Frozen exe runs the same CLI as `-m timetracker.cli`."""
import sys

from timetracker.cli import main

if __name__ == "__main__":
    sys.exit(main())
