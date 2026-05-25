#!/usr/bin/env python
import os
import sys


def main():
    from breathe_esg.env import load_env_files

    load_env_files()
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
