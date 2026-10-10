# -*- coding: utf-8 -*-
"""
IFAS Banking Rails & NACHA ACH File Generator (Sprint 12)
Resolves ADR-011 opaque tokens into banking ACH (NACHA 94-char) batches
for physical bank clearance with air-gapped credential protection.
"""
import sqlite3
import pathlib
from datetime import datetime

DB_PATH = pathlib.Path("ifas_audit_vault.db")
NACHA_OUT_PATH = pathlib.Path("ifas_ach_distribution.ach")

# Offline air-gapped token resolution registry (Delaware FBO Master Custody)
TOKEN_ROUTING_TABLE = {
    "EXT-REF-PENFED-****8800": {
        "routing_num": "256074974",   # PenFed FCU Routing
        "account_num": "9901448800",   # FBO Settlement Trust Acct
        "account_type": "CHECKING",
        "beneficiary": "CARMICHAEL LINEAGE FBO TRUST"
    },
    "EXT-REF-FBO-FOUNDER-****8800": {
        "routing_num": "256074974",
        "account_num": "9901448801",
        "account_type": "CHECKING",
        "beneficiary": "FOUNDER CAPITAL RESERVE"
    }
}

class NachaBatchBuilder:
    def __init__(self, immediate_origin="123456789", immediate_dest="256074974", company_name="CARMICHAEL TRUST"):
        self.origin = immediate_origin.rjust(10)[:10]
        self.dest = immediate_dest.rjust(10)[:10]
        self.company_name = company_name.ljust(16)[:16]
        self.entries = []

    def add_disbursement(self, routing, account, amount_cents, member_id, trace_num):
        self.entries.append({
            "routing": routing[:8],
            "check_digit": routing[8],
            "account": account.ljust(17)[:17],
            "cents": amount_cents,
            "member_id": member_id.ljust(15)[:15],
            "name": member_id.ljust(22)[:22],
            "trace": str(trace_num).zfill(15)
        })

    def build_file(self):
        now = datetime.utcnow()
        f_date = now.strftime("%y%m%d")
        f_time = now.strftime("%H%M")
        
        # 1. File Header Record (Record Type 1)
        # Length strictly 94 characters
        f_header = f"101 {self.dest} {self.origin}{f_date}{f_time}A094101PENFED            CARMICHAEL LINEAGE TRUST"
        f_header = f_header.ljust(94)[:94]

        # 2. Batch Header Record (Record Type 5)
        b_header = f"5220{self.company_name}                    1{self.origin[:9]}PPDSETTLEMENT{f_date}{f_date}   1{self.dest[:8]}0000001"
        b_header = b_header.ljust(94)[:94]

        entry_lines = []
        entry_hash = 0
        total_credit_cents = 0

        # 3. Entry Detail Records (Record Type 6 - Credit / 22: Checking Credit)
        for e in self.entries:
            entry_hash += int(e["routing"])
            total_credit_cents += e["cents"]
            amt_str = str(e["cents"]).zfill(10)
            e_line = f"622{e['routing']}{e['check_digit']}{e['account']}{amt_str}{e['member_id']}{e['name']}  0{e['trace']}"
            entry_lines.append(e_line.ljust(94)[:94])

        entry_hash_str = str(entry_hash)[-10:].zfill(10)
        tot_credit_str = str(total_credit_cents).zfill(12)
        entry_count = len(self.entries)
        cnt_str = str(entry_count).zfill(6)

        # 4. Batch Control Record (Record Type 8)
        b_control = f"8220{cnt_str}{entry_hash_str}000000000000{tot_credit_str}1{self.origin[:9]}                         {self.dest[:8]}0000001"
        b_control = b_control.ljust(94)[:94]

        # 5. File Control Record (Record Type 9)
        block_count = (len(entry_lines) + 4 + 9) // 10
        f_control = f"9000001{str(block_count).zfill(6)}{cnt_str}{entry_hash_str}000000000000{tot_credit_str}"
        f_control = f_control.ljust(94)[:94]

        records = [f_header, b_header] + entry_lines + [b_control, f_control]
        # Verify 94-char constraint across all records
        for idx, rec in enumerate(records):
            assert len(rec) == 94, f"NACHA Record #{idx+1} length error: expected 94, got {len(rec)}"

        return "\n".join(records), total_credit_cents

def generate_nacha_batch(conn):
    c = conn.cursor()
    # Pull distinct SCMA distributions from gl_journal_lines
    rows = c.execute("""
        SELECT a.account_code, a.account_name, SUM(l.credit_cents)
        FROM gl_journal_lines l
        JOIN gl_accounts a ON l.account_code = a.account_code
        WHERE l.credit_cents > 0 AND a.account_code IN ('3010', '3020')
        GROUP BY a.account_code, a.account_name;
    """).fetchall()

    builder = NachaBatchBuilder()
    trace = 1

    for code, name, total_cents in rows:
        member_id = "SCMA-FOUNDER" if code == "3010" else "SCMA-MEM-0001"
        token = "EXT-REF-PENFED-****8800"
        bank_info = TOKEN_ROUTING_TABLE[token]
        builder.add_disbursement(
            routing=bank_info["routing_num"],
            account=bank_info["account_num"],
            amount_cents=total_cents,
            member_id=member_id,
            trace_num=trace
        )
        trace += 1

    file_content, batch_cents = builder.build_file()
    NACHA_OUT_PATH.write_text(file_content, encoding="utf-8")
    return len(rows), batch_cents

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    item_count, total_cents = generate_nacha_batch(conn)
    conn.close()
    print(f"[✓] Generated NACHA ACH batch file at {NACHA_OUT_PATH}")
    print(f"[✓] Reconciled {item_count} member disbursement lines totaling ${total_cents/100:,.2f}")
