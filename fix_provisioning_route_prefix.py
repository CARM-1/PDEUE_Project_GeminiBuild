import pathlib
import re

target_file = pathlib.Path("backend/app/api/v1/workspace_router.py")
content = target_file.read_text(encoding="utf-8")

# Fix endpoints by prefixing with /api/v1 if registered as plain /operator
replacements = [
    ('@router.get("/operator/roster")', '@workspace_router.get("/api/v1/operator/roster")\n@workspace_router.get("/operator/roster")'),
    ('@router.post("/operator/provision-identity")', '@workspace_router.post("/api/v1/operator/provision-identity")\n@workspace_router.post("/operator/provision-identity")'),
    ('@router.post("/operator/batch-provision")', '@workspace_router.post("/api/v1/operator/batch-provision")\n@workspace_router.post("/operator/batch-provision")'),
    ('@router.post("/operator/transition-role")', '@workspace_router.post("/api/v1/operator/transition-role")\n@workspace_router.post("/operator/transition-role")')
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)

target_file.write_text(content, encoding="utf-8")
print("Prefixes harmonized to /api/v1/operator/* on workspace_router.")