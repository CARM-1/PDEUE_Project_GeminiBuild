import pathlib
p = pathlib.Path('backend/app/api/v1/dashboard.html')
html = urllib.request.urlopen('http://127.0.0.1:8000/dashboard').read().decode('utf-8', errors='ignore')
from backend.app.api.v1.dashboard_template import DASHBOARD_HTML_TEMPLATE
p.write_text(DASHBOARD_HTML_TEMPLATE, encoding='utf-8')
print('Restored canonical dashboard template from source.')
