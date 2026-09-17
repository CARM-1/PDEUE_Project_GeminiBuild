"""PDEUE Chief Administrator Dashboard Template Provider."""
import pathlib

_BASE_DIR = pathlib.Path(__file__).parent
_HTML_PATH = _BASE_DIR / "dashboard.html"

def get_fresh_dashboard_html() -> str:
    return _HTML_PATH.read_text(encoding="utf-8") if _HTML_PATH.exists() else "<html><body>Dashboard Not Found</body></html>"

DASHBOARD_HTML_TEMPLATE = get_fresh_dashboard_html()
