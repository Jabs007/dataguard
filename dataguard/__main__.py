"""Allow running the tool with ``python -m dataguard <csv-file>``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
