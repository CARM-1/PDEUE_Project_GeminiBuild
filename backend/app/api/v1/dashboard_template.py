from pathlib import Path
_HTML_FILE = Path(__file__).parent / 'dashboard.html'
if _HTML_FILE.exists():
    DASHBOARD_HTML_TEMPLATE = _HTML_FILE.read_text(encoding='utf-8')
else:
    DASHBOARD_HTML_TEMPLATE = '<!DOCTYPE html><html><head><title>PDEUE Chief Administrator Workspace</title></head><body><h1>PDEUE Chief Administrator Workspace</h1></body></html>'
