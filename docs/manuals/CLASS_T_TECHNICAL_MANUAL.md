# Class T Technical Infrastructure Manual

**Audience:** T1 Monitor, T2 Engineer, and T3 CTO
**Workspace:** `/admin/tech?tier=T1`, `T2`, or `T3`
**Mission:** maintain reliable services and observable evidence without acquiring financial authority

## 1. Authority model and safe login

Class T claims are capabilities, not cosmetic views. Authenticate with an assigned identity, select only the claim required for the task, and confirm the active-tier badge. Never change a query parameter to simulate promotion. Server authorization remains decisive even if a control is visible.

* **T1 Monitor** has read-only operational telemetry. T1 observes health, cycles, queues, latency, and redacted records; T1 cannot trigger daemons or override financial masking.
* **T2 Engineer** may perform approved service operations such as a daemon cycle and technical diagnosis. T2 still cannot unmask protected financial fields, authorize trades, adjudicate advice, or clear a financial halt.
* **T3 CTO** has the highest technical claim, including T2 operations and the ability to request a temporary Chief Administrator (CA) override for an operationally necessary unmasked view. T3 is not the Chief Administrator and cannot select the founder hat or exercise financial controls.

At start of watch, verify release, UTC clock, health status, worker state, queue depth, last scan and reconciliation timestamps, active incidents, secret lease health, migration revision, and Directive R-12 masking. Treat null or stale telemetry as unknown. Record the starting state before mutation.

## 2. Navigating `/admin/tech`

The console summarizes service health, daemon status, recent dispatches, order ladders, cycle counters, and logs. T1 should use it for detection and escalation. T2 may use enabled cycle controls after checking impact and change authority. T3 may diagnose across services but must keep financial content masked unless the documented override procedure is justified.

Refreshes are projections of backend state. A green indicator is not settlement evidence, and a stopped worker does not establish that venue orders were cancelled. **Directive R-04 Emergency Financial Halt** belongs to financial governance. A technical operator may contain a service but cannot clear or reinterpret R-04. Keep incident timelines explicit about financial halt, internal service state, and external venue state.

## 3. AutonomousScanWorker cycle management

`AutonomousScanWorker` coordinates an internal scan cycle: collect qualified domain data, form candidates, apply governance and risk gates, dispatch eligible work, update position state, stage float sweeps, and emit cycle telemetry. Exact composition depends on qualification and operating mode. A cycle is not permission to trade; all downstream gates remain authoritative.

Before a T2/T3 manual cycle:

1. Confirm a ticket or runbook reason and scope.
2. Confirm no conflicting deployment, migration, reconciliation, or active incident.
3. Read circuit-breaker and R-04 state. Never cycle to bypass a halt.
4. Verify source freshness and venue adapter health.
5. Capture prior cycle count, queue depth, order count, and outbox sequence.
6. Trigger once and retain the correlation identifier.
7. Compare post-cycle telemetry and inspect reason codes.

The worker must fail closed when its circuit breaker is tripped. Repeatedly clicking a cycle control can duplicate pressure even when economic actions are idempotent. If a request times out, first determine whether the cycle executed. Never assume timeout means no effect.

Start and stop operations should be bounded, observable, and reversible. A graceful stop prevents new cycles and allows in-flight internal work to reach a safe boundary. Escalate if a worker cannot stop, reports overlapping cycles, loses its heartbeat, or emits noncontiguous telemetry. Preserve logs before restart.

## 4. SettlementReconciler cycle management

`SettlementReconciler` compares venue outcomes, internal positions, settled cash, and accounting events. Its purpose is convergence, not profit creation. Reconciliation should be idempotent: replaying the same confirmed settlement must not create another economic result.

Before a manual reconciliation, record venue, market and order identifiers, last known status, internal position version, last accounting sequence, and data timestamp. Ensure the venue result is final enough for the relevant adapter. Run one bounded cycle. Review matched, pending, corrected, disputed, and failed counts. For every correction, confirm the causal external fact and durable audit link.

Apply **ADR-008, Exact-Cent Conservation**: authoritative monetary values use integer cents; waterfall components must sum to the eligible settled whole. Never resolve a mismatch using floating-point rounding or an untracked database edit. Apply **ADR-011, Signed Accounting Outbox and Custodial Boundary**: reconciliation may stage a signed accounting envelope, but must not call a bank with stored credentials. Validate sequence, signature, schema, idempotency, and acknowledgement separately.

If reconciliation diverges, stop retries, isolate affected events, identify the last common checkpoint, compare venue facts and internal versions, and escalate to financial authority when balances or disbursements are affected. T2/T3 may repair service mechanics; only authorized financial roles approve economic correction.

## 5. Venue token buckets and backoff

Kalshi and Polymarket each have an independent token bucket limited to **10 requests per second**. Consuming all ten tokens causes the next request to be denied with a bounded retry interval; the implementation adds jitter (for example, a maximum test interval of 0.125 seconds) to prevent synchronized retry storms. One venue exhausting its bucket must not consume the other venue's capacity.

Adapters must call the limiter before network work. On denial, honor `retry_after_seconds`, wait, and retry through the bounded policy. Do not busy-loop, create parallel clients to evade the limit, or disable jitter. Observe HTTP `429`, timeout, latency, and error-rate signals. Server-supplied backoff that is longer than local timing wins. Exponential backoff should be capped, jittered, and limited by an overall retry budget.

Retries must preserve the original correlation and idempotency identifiers. For reads, stale-data rules still apply. For order or cancellation writes, query authoritative state before retry when the response is ambiguous. A local service halt does not prove external cancellation. Open the circuit when errors exceed policy, allow a controlled half-open probe, and return to closed state only after demonstrated recovery.

## 6. Directive R-12 Financial Masking

**Directive R-12, Least-Privilege Financial Masking**, keeps tenant balances, exposure, and sensitive accounting values out of routine technical telemetry. Redaction is performed server-side and is immutable to T1 and T2. Expected values such as `$****.**` are not CSS decoration and cannot be reconstructed from logs, metrics, DOM state, adjacent endpoints, or exports.

R-12 protects both direct and derivative disclosure. Do not log payloads that permit a balance to be inferred from before/after values, quantities, per-tenant labels, or error messages. Use aggregate service metrics with bounded cardinality. Redaction must survive refresh, export, error paths, and reconnect. A missing value is not zero.

### T3 CA Override cryptographic procedure

A T3 operator may unmask only when diagnosis genuinely requires financial values and an authorized Chief Administrator provides a valid override token through the approved secret channel:

1. Open an incident or change record stating purpose, tenant scope, fields, operator, and time limit.
2. Obtain explicit CA approval. The CA generates or releases a cryptographically protected, short-lived token bound to purpose and scope; never reuse the development example token in production.
3. T3 opens the console's CA Override dialog and enters the token once. Do not paste it into chat, logs, shell history, tickets, or source.
4. The server verifies signature or keyed digest, audience, issuer, scope, expiry, nonce, and T3 claim. Failure leaves masking active and must be audited.
5. A successful grant is temporary and page-scoped. Confirm the visible active-grant indicator and access only the approved evidence.
6. Capture conclusions, not unrestricted raw balances. Avoid screenshots and downloads.
7. Revoke and remask immediately when the task ends; refresh to verify redaction. Expiry, logout, navigation, or service restart must not create a persistent grant.
8. Record revocation and have the CA review use.

The override changes visibility, not authority. T3 still cannot move money, raise risk, approve a proposal, or clear R-04. If token validation behaves unexpectedly, stop, preserve sanitized evidence, revoke the token, and treat it as a security incident.

## 7. AWS CloudWatch logs integration

Applications should emit structured JSON to standard output or the approved logging handler. The container or workload agent forwards records to an environment-specific CloudWatch log group and stream. Include timestamp, severity, service, release, environment, correlation ID, cycle ID, event type, and sanitized reason code. Exclude secrets, tokens, banking data, raw authorization headers, tenant balances, and unredacted payloads.

Create retention, encryption, access, and export policies through infrastructure-as-code. Apply least-privilege IAM: workloads write only to their designated streams; T1 reads sanctioned groups; administrative changes require the approved engineering path. Use metric filters for worker heartbeat loss, reconciliation failure, signature failure, outbox backlog, rate-limit pressure, and repeated override denial. Alarms should link to this runbook and avoid tenant identifiers in notification text.

During an incident, search by correlation and UTC window, export only sanitized evidence, and record the query. CloudWatch receipt confirms logging transport, not business success. Compare logs with service telemetry and authoritative records.

## 8. Prometheus and Grafana RSS metrics

Expose a protected Prometheus scrape endpoint or approved collector for operational metrics. Recommended series include process resident set size (RSS), CPU, worker heartbeat age, cycle duration, cycle failures, queue depth, reconciliation lag, outbox backlog, rate-limit denials, adapter latency, circuit state, and request outcomes. Prefer standard process RSS metrics where available.

Labels must be low-cardinality and nonfinancial: service, environment, worker type, venue, and bounded status. Never label by member, SCMA, order, token, proposal, or raw exception. Counters increase monotonically, gauges represent current values, and histograms use reviewed buckets. Protect the scrape path; metrics are not a public endpoint.

Grafana dashboards should show current RSS, rate of growth, restart markers, cycle latency, error ratios, and reconciliation lag. Alert on sustained conditions, not one noisy sample. For a suspected leak, compare RSS slope with cycle and queue volume, capture a bounded profile under change control, stop or roll the service if safety thresholds require it, and verify recovery. Do not expose financial payloads to diagnose memory.

## 9. Alembic CLI migration runbook

Database schema changes use Alembic from the `backend` environment. Review the revision, downgrade path, locks, data conversion, and compatibility window. Back up according to environment policy and test on a production-shaped nonproduction copy. During an approved maintenance window, confirm application quiescence where required, inspect the current revision, then apply the reviewed target with `alembic upgrade head`.

After migration, inspect the revision, run schema and application tests, start one instance, verify health and reconciliation, then roll out gradually. Never stamp a database merely to conceal a failed migration. If rollback is safe and reviewed, use the specific downgrade target; otherwise restore or forward-fix under the incident plan. SQLite development behavior does not prove production database locking behavior.

Useful controlled commands are `alembic current`, `alembic history`, `alembic upgrade head`, and an explicitly reviewed `alembic downgrade <revision>`. Run them from `backend` with the correct configuration and secret lease. Never embed database credentials in the command or commit them.

## 10. AWS Secrets Manager integration

Store exchange credentials, signing material, database secrets, and production override-verification material in AWS Secrets Manager, not source, images, `.env` files, logs, or tickets. Workload identity should retrieve only named secrets needed by that service. Prefer short leases, rotation, version staging, encryption with a controlled KMS key, and audit through CloudTrail.

At startup, the secrets broker resolves approved references and holds values only as long as necessary. Logs should contain a secret name or opaque lease identifier, never its value. Rotation procedure: create a new version; validate it in a bounded canary; promote it; verify old and new dependent services; revoke the old credential; and record completion. For compromise, revoke first, rotate, reconcile actions taken with the credential, and investigate access history.

R-12 override tokens should be short-lived signed artifacts, not a static universal password. AWS Secrets Manager may protect signing or verification material, but routine operators should not retrieve raw keys. A secret access failure must fail closed and alert; hard-coded fallback credentials are prohibited.

## 11. Technical incident matrix

For heartbeat loss, T1 records timestamps and alerts T2. T2 checks queue and graceful-stop state, preserves logs, and performs an approved restart. For repeated recurrence, T3 owns root cause. For rate limiting, reduce concurrency and honor backoff rather than adding clients. For settlement divergence, isolate retries and involve financial authority. For outbox signature failure, quarantine the event and signing path. For an R-12 leak, revoke access, preserve sanitized evidence, rotate affected material, and invoke security response.

If capital might be at risk, notify the Chief Administrator to consider R-04. Technical staff may stop internal services immediately within incident authority, but must state clearly that external cancellation was not authorized or attempted unless separately proven.

## 12. Change, verification, and handoff

Every change needs an owner, review, rollback, qualification evidence, and observation window. Use headless automated tests and approved linters; never diagnose production by inventing transactions. Confirm workers, reconciliation, rate limiters, masking, migrations, metrics, logging, and secret retrieval after deployment.

At handoff, report tier, release, service state, cycles, reconciliation lag, circuit states, R-04 state, rate-limit anomalies, migration revision, RSS trend, outbox backlog, active secret rotations, active or revoked override grants, incidents, and next owner. Do not include masked values or tokens.

Class T protects the machinery and evidence. It does not own the money. Maintaining that boundary—especially under pressure—is the central technical control.

## PDEUE University curriculum alignment (Canonical Lexicon v0.5)

This manual is the field guide for the **Institute of Systems Engineering (Class T Operators T1–T3)**. Chapter 4 of `/companion` visualizes the boundary but does not emit production instructions. The priority eviction engine is fixed at **N=12** admitted items: deterministic rank and tie-break rules evict the lowest-priority candidate rather than silently expanding capacity. Preserve the candidate evidence and reason code for every eviction.

The **ADR-011 air-gap** permits only signed, sequenced, schema-valid, idempotent accounting envelopes such as IF-038 to cross from the platform to the downstream accounting adapter. It never carries banking credentials and an acknowledgement is not proof of settlement. For SQLite deployments, retain WAL operation with `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=FULL`, a bounded `busy_timeout`, foreign keys enabled, and a single-writer discipline. Monitor and checkpoint the WAL through an approved maintenance path; do not delete `-wal` or `-shm` files from a live database.
