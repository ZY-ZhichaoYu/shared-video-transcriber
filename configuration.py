"""Optional project-local settings; explicit process environment always wins."""
from pathlib import Path
from dotenv import load_dotenv


def load_settings(directory=None):
    root=Path(directory) if directory else Path(__file__).resolve().parent
    load_dotenv(root/'.env',override=False,encoding='utf-8-sig',interpolate=False)
