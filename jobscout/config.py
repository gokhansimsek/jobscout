"""Project paths and process setup shared by the CLI."""

import io
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def setup() -> None:
    """Prepare the process for a CLI run.

    Loads ``.env`` into the environment and switches stdout to UTF-8 so the
    Windows console can print Turkish characters.
    """
    load_dotenv(ROOT / ".env")
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
