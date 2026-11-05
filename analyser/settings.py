"""Where things are, from one place (used by the analyser).

Order for every setting: environment variable, then the local `config.yaml` in the project root (not in git), then a default.

  data_root    folder holding DOB/ Marital/ Marriage-Divorce/ (the requests) and Electors/    env CRID_WORK_ROOT   default <project>/data
  electors_db  the electoral roll database                                                                  env ELECTORS_DB      default <data_root>/Electors/electors.db
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yaml"


def _config():
    if not CONFIG.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def _path(value):
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else ROOT / p


def data_root():
    value = os.environ.get("CRID_WORK_ROOT") or _config().get("data_root")
    return _path(value) if value else ROOT / "data"


def electors_db():
    value = os.environ.get("ELECTORS_DB") or _config().get("electors_db")
    return _path(value) if value else data_root() / "Electors" / "electors.db"
