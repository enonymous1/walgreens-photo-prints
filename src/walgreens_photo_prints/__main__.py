"""Allow ``python -m walgreens_photo_prints``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
