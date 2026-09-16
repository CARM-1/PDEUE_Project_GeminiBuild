import pathlib

wr_path = pathlib.Path("backend/app/api/v1/workspace_router.py")
content = wr_path.read_text(encoding="utf-8")

old_route = '@workspace_router.get("/operator/orc/dossier")'
new_routes = '@workspace_router.get("/orc/dossier")\n@workspace_router.get("/operator/orc/dossier")'

if old_route in content:
    content = content.replace(old_route, new_routes)
    wr_path.write_text(content, encoding="utf-8")
    print("Successfully patched workspace_router.py with dual ORC routes.")
else:
    print("Route pattern already patched or dual routes present.")