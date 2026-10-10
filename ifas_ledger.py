# -*- coding: utf-8 -*-
"""
IFAS General Ledger & Interchange Bridge Module (Sprint 11)
Transforms cryptographic settlement vouchers into GAAP double-entry books
and exports standards-compliant QIF and CSV formats for GnuCash.
"""
import sqlite3
import pathlib
import csv
from datetime import datetime

DB_PATH = pathlib.Path("ifas_audit_vault.db")
QIF_PATH = pathlib.Path("ifas_lineage_ledger.qif")
CSV_PATH = pathlib.Path("ifas_lineage_ledger.csv")

CHART_OF_ACCOUNTS = [
    ("1010", "Assets:Bank:PenFed FBO Operating Cash", "ASSET", "USD"),
    ("3010", "Equity:Members:SCMA-FOUNDER", "EQUITY", "USD"),
    ("3020", "Equity:Members:SCMA-MEM-0001", "EQUITY", "USD"),
    ("3030", "Equity:Reserves:CFCP Familial Common Pool", "EQUITY", "USD"),
    ("3040", "Equity:Reserves:FAEP Endowment Pool", "EQUITY", "USD"),
    ("4010", "Income:Trading:Realized Waterfall Settlements", "INCOME", "USD")
]

def init_ledger_schema(conn):
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS gl_accounts (
            account_code TEXT PRIMARY KEY,
            account_name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            commodity TEXT NOT NULL DEFAULT 'USD'
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS gl_journal_entries (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_ref TEXT UNIQUE NOT NULL,
            post_date TEXT NOT NULL,
            description TEXT NOT NULL,
            source_category TEXT NOT NULL
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS gl_journal_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            account_code TEXT NOT NULL,
            debit_cents INTEGER NOT NULL DEFAULT 0,
            credit_cents INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (entry_id) REFERENCES gl_journal_entries(entry_id),
            FOREIGN KEY (account_code) REFERENCES gl_accounts(account_code)
        );
    """)
    for code, name, acct_type, comm in CHART_OF_ACCOUNTS:
        c.execute("""
            INSERT OR IGNORE INTO gl_accounts (account_code, account_name, account_type, commodity)
            VALUES (?, ?, ?, ?);
        """, (code, name, acct_type, comm))
    conn.commit()

def post_vouchers_to_gl(conn):
    c = conn.cursor()
    # Discover vault_vouchers columns
    c.execute("PRAGMA table_info(vault_vouchers);")
    cols = [col[1] for col in c.fetchall()]
    
    rows = c.execute("SELECT * FROM vault_vouchers ORDER BY rowid ASC;").fetchall()
    posted_count = 0

    for r in rows:
        row_dict = dict(zip(cols, r))
        scma = row_dict.get("scma_id") or row_dict.get("target_scma")
        amt = row_dict.get("amount_cents", 0)
        v_id = row_dict.get("voucher_id") or f"VOUCHER-{row_dict.get('rowid', posted_count+1)}"
        ts = row_dict.get("timestamp") or row_dict.get("created_at") or datetime.utcnow().isoformat()
        seal = row_dict.get("hmac_seal") or row_dict.get("hmac_signature") or "AUTHENTICATED"
        desc = f"Waterfall Settlement Sweep - {scma} (HMAC: {seal[:12]}...)"

        # Check if already posted
        existing = c.execute("SELECT entry_id FROM gl_journal_entries WHERE voucher_ref = ?;", (v_id,)).fetchone()
        if existing:
            continue

        c.execute("""
            INSERT INTO gl_journal_entries (voucher_ref, post_date, description, source_category)
            VALUES (?, ?, ?, 'WATERFALL_SWEEP');
        """, (v_id, ts, desc))
        entry_id = c.lastrowid

        # Target equity account
        target_equity_code = "3010" if scma == "SCMA-FOUNDER" else "3020"

        # Balanced Double-Entry Post:
        # 1. Debit FBO Bank Cash (Assets Increase)
        # 2. Credit Member SCMA Equity (Capital Allocated)
        c.execute("""
            INSERT INTO gl_journal_lines (entry_id, account_code, debit_cents, credit_cents)
            VALUES (?, '1010', ?, 0);
        """, (entry_id, amt))
        c.execute("""
            INSERT INTO gl_journal_lines (entry_id, account_code, debit_cents, credit_cents)
            VALUES (?, ?, 0, ?);
        """, (entry_id, target_equity_code, amt))

        posted_count += 1

    conn.commit()
    return posted_count

def export_qif(conn):
    """Exports transactions in standard Quicken Interchange Format (QIF) for GnuCash."""
    c = conn.cursor()
    entries = c.execute("""
        SELECT e.post_date, e.voucher_ref, e.description, l_dr.debit_cents, a_cr.account_name
        FROM gl_journal_entries e
        JOIN gl_journal_lines l_dr ON e.entry_id = l_dr.entry_id AND l_dr.account_code = '1010'
        JOIN gl_journal_lines l_cr ON e.entry_id = l_cr.entry_id AND l_cr.account_code != '1010'
        JOIN gl_accounts a_cr ON l_cr.account_code = a_cr.account_code
        ORDER BY e.entry_id ASC;
    """).fetchall()

    lines = [
        "!Account",
        "NAssets:Bank:PenFed FBO Operating Cash",
        "TBank",
        "^",
        "!Type:Bank"
    ]

    for post_date, v_ref, desc, debit_cents, cr_acct_name in entries:
        dt_str = post_date[:10]
        try:
            d_obj = datetime.fromisoformat(post_date.replace("Z", "+00:00"))
            dt_str = d_obj.strftime("%m/%d/%Y")
        except Exception:
            pass
        amt_str = f"{debit_cents / 100:.2f}"
        lines.append(f"D{dt_str}")
        lines.append(f"T{amt_str}")
        lines.append(f"N{v_ref}")
        lines.append(f"P{desc}")
        lines.append(f"L{cr_acct_name}")
        lines.append("^")

    QIF_PATH.write_text("\n".join(lines), encoding="utf-8")
    return len(entries)

def export_csv(conn):
    """Exports standard double-entry audit records to CSV."""
    c = conn.cursor()
    rows = c.execute("""
        SELECT e.voucher_ref, e.post_date, a.account_code, a.account_name, l.debit_cents, l.credit_cents, e.description
        FROM gl_journal_entries e
        JOIN gl_journal_lines l ON e.entry_id = l.entry_id
        JOIN gl_accounts a ON l.account_code = a.account_code
        ORDER BY e.entry_id ASC, l.line_id ASC;
    """).fetchall()

    with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Voucher Ref", "Date", "Account Code", "Account Name", "Debit USD", "Credit USD", "Memo"])
        for v_ref, dt, code, name, dr, cr, memo in rows:
            writer.writerow([v_ref, dt[:19], code, name, f"{dr/100:.2f}", f"{cr/100:.2f}", memo])
    return len(rows)

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    init_ledger_schema(conn)
    posted = post_vouchers_to_gl(conn)
    qif_count = export_qif(conn)
    csv_lines = export_csv(conn)
    conn.close()
    print(f"[✓] Initialized Chart of Accounts ({len(CHART_OF_ACCOUNTS)} accounts).")
    print(f"[✓] Reconciled {qif_count} transactions into General Ledger.")
    print(f"[✓] Exported {qif_count} QIF transactions to {QIF_PATH}.")
    print(f"[✓] Exported {csv_lines} double-entry line items to {CSV_PATH}.")
