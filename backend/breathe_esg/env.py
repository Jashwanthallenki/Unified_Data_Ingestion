import os
from pathlib import Path

BACKEND_ENV_IGNORED_KEYS = {"DATABASE_URL"}


def load_env_files() -> None:
    """Load local .env files for development without overriding real env vars."""
    try:
        from dotenv import dotenv_values, load_dotenv
    except ImportError:
        return

    backend_dir = Path(__file__).resolve().parent.parent
    repo_root = backend_dir.parent

    root_env = repo_root / ".env"
    if root_env.exists():
        load_dotenv(root_env, override=False)

    backend_env = backend_dir / ".env"
    if backend_env.exists():
        for key, value in dotenv_values(backend_env).items():
            if key in BACKEND_ENV_IGNORED_KEYS or value is None or key in os.environ:
                continue
            os.environ[key] = value
