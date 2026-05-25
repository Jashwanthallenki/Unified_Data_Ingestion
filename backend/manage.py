#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main():
    # Load .env from repo root if present (dev convenience).
    try:
        from dotenv import load_dotenv

        repo_root = Path(__file__).resolve().parent.parent
        env_path = repo_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "breathe_esg.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Did you `pip install -r requirements.txt`?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
