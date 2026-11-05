"""Create backend/.env from .env.example with a random JWT secret."""

import os
import re
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXAMPLE_PATH = BACKEND_DIR / ".env.example"
ENV_PATH = BACKEND_DIR / ".env"


def main() -> int:
    content = re.sub(
        r"^JWT_SECRET=.*$",
        f"JWT_SECRET={secrets.token_hex(32)}",
        EXAMPLE_PATH.read_text(),
        flags=re.MULTILINE,
    )
    try:
        # O_EXCL so an existing file is never replaced, 0o600 so only the owner can read it.
        fd = os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{ENV_PATH} already exists, not overwriting it", file=sys.stderr)
        return 1
    with os.fdopen(fd, "w") as env_file:
        env_file.write(content)
    print(f"Created {ENV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
