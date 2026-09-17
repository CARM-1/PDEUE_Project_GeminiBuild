"""
PDEUE Chief Administrator Dashboard Template Provider.
Loads pure HTML directly from disk to ensure clean separation and zero string escaping errors.
"""
import pathlib

_BASE_DIR = pathlib.Path(__file__).parent
_HTML_PATH = _BASE_DIR / "dashboard.html"
if not _HTML_PATH.exists():
    _HTML_PATH = _BASE_DIR.parent.parent / "static" / "dashboard.html"

DASHBOARD_HTML_TEMPLATE = _HTML_PATH.read_text(encoding="utf-8") if _HTML_PATH.exists() else "<html><body><h1>PDEUE Chief Administrator Workspace</h1></body></html>"
