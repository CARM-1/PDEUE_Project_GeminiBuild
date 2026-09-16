import pathlib

router_path = pathlib.Path("backend/app/api/v1/workspace_router.py")
if router_path.exists():
    text = router_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "get(\"/dashboard\"" in line or "dashboard.html" in line or "DASHBOARD_HTML" in line:
            print("Router mapping line:", line.strip())
else:
    print("Router not found at path.")