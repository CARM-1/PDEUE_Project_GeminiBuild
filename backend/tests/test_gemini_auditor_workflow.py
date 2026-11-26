"""Verification tests for Layer A Autonomous PR Auditor (GEMINI.md + GitHub Actions)."""
import os
from pathlib import Path
import subprocess

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "gemini-pr-auditor.yml"
GEMINI_MD_PATH = REPO_ROOT / "GEMINI.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}"
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), "Workflow YAML must parse to a mapping"
    return parsed


def _get_triggers(workflow: dict) -> dict:
    # PyYAML (YAML 1.1) parses unquoted `on:` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), "Workflow `on:` trigger mapping is required"
    return triggers


def test_workflow_parses_and_triggers_only_on_ring1_alpha_pull_requests():
    workflow = _load_workflow()
    triggers = _get_triggers(workflow)

    assert set(triggers.keys()) == {"pull_request"}, (
        f"Workflow must trigger ONLY on pull_request (zero idle token burn); got {set(triggers.keys())}"
    )

    pr_trigger = triggers["pull_request"]
    assert pr_trigger["branches"] == ["ring1-alpha"], (
        f"PR auditor must target ONLY ring1-alpha; got {pr_trigger.get('branches')}"
    )
    assert set(pr_trigger["types"]) == {"opened", "synchronize", "reopened"}


def test_workflow_has_concurrency_and_least_privilege_permissions():
    workflow = _load_workflow()

    concurrency = workflow.get("concurrency")
    assert isinstance(concurrency, dict), "Workflow must define concurrency guardrails"
    assert concurrency.get("cancel-in-progress") is True
    assert "github.event.pull_request.number" in str(concurrency.get("group", ""))

    permissions = workflow.get("permissions")
    assert permissions == {
        "contents": "read",
        "pull-requests": "write",
        "issues": "write",
    }, f"Workflow permissions must remain least-privilege; got {permissions}"


def test_workflow_uses_run_gemini_cli_safely_with_empty_key_guardrail():
    raw_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = _load_workflow()

    jobs = workflow.get("jobs", {})
    assert len(jobs) == 1, "Expected a single stateless audit job"
    job = next(iter(jobs.values()))
    steps = job.get("steps", [])
    assert steps, "Audit job must define steps"

    # Secret availability check must happen first and gate downstream steps cleanly.
    check_step = steps[0]
    assert check_step.get("id") == "check_secret"
    assert "${{ secrets.GEMINI_API_KEY }}" in str(check_step.get("env", {}).get("GEMINI_API_KEY", ""))

    checkout_steps = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkout_steps) == 1
    assert checkout_steps[0].get("with", {}).get("persist-credentials") is False
    assert "steps.check_secret.outputs.enabled == 'true'" in str(checkout_steps[0].get("if", ""))

    gemini_steps = [
        s for s in steps if s.get("uses") == "google-github-actions/run-gemini-cli@v0"
    ]
    assert len(gemini_steps) == 1, "Expected google-github-actions/run-gemini-cli@v0 step"
    gemini_step = gemini_steps[0]
    assert "steps.check_secret.outputs.enabled == 'true'" in str(gemini_step.get("if", ""))
    assert gemini_step.get("with", {}).get("gemini_api_key") == "${{ secrets.GEMINI_API_KEY }}"
    assert gemini_step.get("env", {}).get("GITHUB_TOKEN") == "", (
        "LLM step must not receive write-capable GITHUB_TOKEN"
    )

    prompt = str(gemini_step.get("with", {}).get("prompt", ""))
    for required_phrase in (
        "GEMINI.md",
        "git diff origin/ring1-alpha...HEAD",
        "ADR-008",
        "ADR-011",
        "OBSERVED_TRADE",
        "CONFIRMED_OWN_FILL",
        "VERDICT: PASS",
        "VERDICT: RETRY",
        "VERDICT: ESCALATE",
    ):
        assert required_phrase in prompt, f"Auditor prompt missing required check: {required_phrase}"

    # Read-only guarantee: workflow must never push commits or merge PRs.
    assert "git push" not in raw_text
    assert "gh pr merge" not in raw_text


def test_workflow_gracefully_handles_transient_429_and_503_errors(tmp_path: Path):
    workflow = _load_workflow()
    job = next(iter(workflow["jobs"].values()))
    steps = job["steps"]

    gemini_step = next(s for s in steps if s.get("id") == "gemini_auditor")
    assert gemini_step.get("continue-on-error") is True, (
        "gemini_auditor step must set continue-on-error: true so transient 429/503 errors can be classified gracefully"
    )

    error_step = next(s for s in steps if s.get("id") == "handle_auditor_error")
    assert "steps.check_secret.outputs.enabled == 'true'" in str(error_step.get("if", ""))
    assert "steps.gemini_auditor.outcome == 'failure'" in str(error_step.get("if", ""))
    assert error_step.get("env", {}).get("AUDIT_ERROR") == "${{ steps.gemini_auditor.outputs.error }}"
    script = str(error_step.get("run", ""))
    assert "::warning" in script
    assert "429" in script and "503" in script

    comment_step = next(s for s in steps if s.get("name") == "Post PR Audit Comment")
    assert "steps.check_secret.outputs.enabled == 'true'" in str(comment_step.get("if", ""))
    assert "steps.gemini_auditor.outcome == 'success'" in str(comment_step.get("if", ""))

    # Execute the exact workflow error-handler script against 429, 503, and non-transient errors.
    summary_file = tmp_path / "step_summary.md"
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GITHUB_STEP_SUMMARY": str(summary_file),
    }

    # 1. Transient HTTP 429 (quota exhausted) -> ::warning:: + exit 0
    quota_429 = subprocess.run(
        ["bash", "-c", script],
        env={
            **base_env,
            "AUDIT_ERROR": '{"type":"Error","message":"You have exhausted your daily quota on this model.","code":429}',
            "AUDIT_SUMMARY": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert quota_429.returncode == 0, f"HTTP 429 should exit green: {quota_429.stdout} {quota_429.stderr}"
    assert "::warning" in quota_429.stdout

    # 2. Transient HTTP 503 (high demand) -> ::warning:: + exit 0
    demand_503 = subprocess.run(
        ["bash", "-c", script],
        env={
            **base_env,
            "AUDIT_ERROR": '{"type":"Error","message":"This model is currently experiencing high demand.","code":503}',
            "AUDIT_SUMMARY": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert demand_503.returncode == 0, f"HTTP 503 should exit green: {demand_503.stdout} {demand_503.stderr}"
    assert "::warning" in demand_503.stdout

    # 3. Non-transient error (e.g., invalid API key HTTP 401) -> ::error:: + non-zero exit
    auth_401 = subprocess.run(
        ["bash", "-c", script],
        env={
            **base_env,
            "AUDIT_ERROR": '{"type":"Error","message":"API key not valid.","code":401}',
            "AUDIT_SUMMARY": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert auth_401.returncode != 0, "Non-transient errors must still fail the workflow"
    assert "::error" in auth_401.stdout


def test_gitignore_includes_gemini_and_gha_credentials():
    lines = {
        line.strip()
        for line in GITIGNORE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert ".gemini/" in lines
    assert "gha-creds-*.json" in lines


def test_gemini_md_preserves_charter_and_encodes_brief01_invariants():
    content = GEMINI_MD_PATH.read_text(encoding="utf-8")

    # Preserve existing core PDEUE invariants.
    for existing_invariant in (
        "ADR-008",
        "ADR-011",
        "ADR-012",
        "87% SCMA / 10% CFCP / 3% FAEP",
        "AUTH-01",
        "AUTH-04",
        "3-Retry Circuit Breaker",
        "ring1-alpha",
    ):
        assert existing_invariant in content, f"Existing invariant removed from GEMINI.md: {existing_invariant}"

    # Verify Brief #01 ratified invariants and PR audit verdict format.
    for brief01_clause in (
        "Brief #01 Microstructure & Statistical Invariants (Ratified)",
        "price_pips",
        "$0.0001",
        "qty_centi",
        "0.01",
        "micro_dollars",
        "$0.000001",
        "float()",
        "uniform 1c-grid, zero-maker-fee Kalshi series",
        "No print, no fill",
        "OBSERVED_TRADE",
        "CONFIRMED_OWN_FILL",
        "4c–10c",
        "3c",
        "1c–2c",
        "BENCHMARK_ONLY",
        "Days 1–8 Train / Day 9 Embargo / Days 10–14 Sealed Holdout",
        "$100 Founder Micro-Pilot",
        "$5 max order / $10 max cumulative loss",
        "e >= 20",
        "VERDICT: PASS",
        "VERDICT: RETRY",
        "VERDICT: ESCALATE",
    ):
        assert brief01_clause in content, f"Brief #01 clause missing from GEMINI.md: {brief01_clause}"
