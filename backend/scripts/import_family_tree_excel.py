#!/usr/bin/env python3
"""Standalone deterministic Excel-to-JSON importer for the PDEUE Interactive Family Tree.

Reads normalized `People` and `Relationships` sheets from an Excel `.xlsx` workbook
(matching `Family_Tree_With_Relationship_Calculator_v3_2_Excel2019.xlsx`), cleanly strips
generational suffixes (`Jr.`, `Sr.`, `II`, `III`, `IV`, `1`, etc.) out of `surname` into
`suffix`, strips any contact/PII columns, validates zero broken ID references, and writes
a deterministic `family_tree_seed.json`.

Works with `openpyxl` when installed and falls back automatically to a pure-Python
standard-library OOXML (`zipfile` + `xml.etree.ElementTree`) reader with zero third-party
dependencies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
import zipfile

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_OUTPUT_PATH = BACKEND_DIR / "app" / "static" / "data" / "family_tree_seed.json"

_SUFFIX_RE = re.compile(r"(?:,?\s+)(Jr\.?|Sr\.?|II|III|IV|V|1|2|3)$", re.IGNORECASE)
_COL_REF_RE = re.compile(r"^([A-Z]+)")

_TRUTHY_STRINGS = frozenset({"1", "true", "yes", "y", "deceased", "dead", "x"})
_FALSY_STRINGS = frozenset({"0", "false", "no", "n", "living", "alive", ""})


def normalize_suffix_token(raw: Any) -> str:
    token = " ".join(str(raw or "").strip().split())
    if not token:
        return ""
    lowered = token.rstrip(".").lower()
    if lowered == "jr":
        return "Jr."
    if lowered == "sr":
        return "Sr."
    if lowered in {"ii", "iii", "iv", "v"}:
        return lowered.upper()
    return token[:16]


def normalize_surname_and_suffix(surname: Any, suffix: Any = "") -> Tuple[str, str]:
    """Cleanly separate trailing generational suffixes (Jr., Sr., 1, II, III, IV) from surname."""
    clean_surname = " ".join(str(surname or "").strip().split())
    clean_suffix = normalize_suffix_token(suffix)
    match = _SUFFIX_RE.search(clean_surname)
    if match:
        extracted = normalize_suffix_token(match.group(1))
        clean_surname = clean_surname[: match.start()].strip().rstrip(",")
        if not clean_suffix:
            clean_suffix = extracted
    return clean_surname, clean_suffix


def _col_letters_to_index(letters: str) -> int:
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _read_xlsx_via_stdlib(xlsx_path: Path) -> Dict[str, List[List[Any]]]:
    """Pure-Python OOXML `.xlsx` sheet reader (no third-party dependencies required)."""
    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_pkg_rel = "http://schemas.openxmlformats.org/package/2006/relationships"

    sheets_out: Dict[str, List[List[Any]]] = {}
    with zipfile.ZipFile(xlsx_path, "r") as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst_root.findall(f"{{{ns_main}}}si"):
                parts = [t.text or "" for t in si.iter(f"{{{ns_main}}}t")]
                shared_strings.append("".join(parts))

        rels_map: Dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in zf.namelist():
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rels_root.findall(f"{{{ns_pkg_rel}}}Relationship"):
                rid = rel.attrib.get("Id", "")
                target = rel.attrib.get("Target", "").lstrip("/")
                if target and not target.startswith("xl/"):
                    target = f"xl/{target}"
                rels_map[rid] = target

        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets_el = wb_root.find(f"{{{ns_main}}}sheets")
        if sheets_el is None:
            return sheets_out

        for sheet_el in sheets_el.findall(f"{{{ns_main}}}sheet"):
            name = sheet_el.attrib.get("name", "")
            rid = sheet_el.attrib.get(f"{{{ns_rel}}}id", "")
            target = rels_map.get(rid, "")
            if not target or target not in zf.namelist():
                continue

            ws_root = ET.fromstring(zf.read(target))
            sheet_data = ws_root.find(f"{{{ns_main}}}sheetData")
            rows: List[List[Any]] = []
            if sheet_data is not None:
                for row_el in sheet_data.findall(f"{{{ns_main}}}row"):
                    cells_by_idx: Dict[int, Any] = {}
                    next_idx = 0
                    for c_el in row_el.findall(f"{{{ns_main}}}c"):
                        ref = c_el.attrib.get("r", "")
                        col_m = _COL_REF_RE.match(ref)
                        c_idx = _col_letters_to_index(col_m.group(1)) if col_m else next_idx
                        next_idx = c_idx + 1

                        c_type = c_el.attrib.get("t", "")
                        val: Any = None
                        if c_type == "inlineStr":
                            is_el = c_el.find(f"{{{ns_main}}}is")
                            if is_el is not None:
                                val = "".join(t.text or "" for t in is_el.iter(f"{{{ns_main}}}t"))
                        else:
                            v_el = c_el.find(f"{{{ns_main}}}v")
                            raw_v = v_el.text if v_el is not None else None
                            if raw_v is None:
                                val = None
                            elif c_type == "s":
                                s_idx = int(raw_v)
                                val = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else ""
                            elif c_type == "b":
                                val = raw_v == "1"
                            elif c_type == "str":
                                val = raw_v
                            else:
                                try:
                                    f_val = float(raw_v)
                                    val = int(f_val) if f_val.is_integer() else f_val
                                except ValueError:
                                    val = raw_v
                        cells_by_idx[c_idx] = val
                    if cells_by_idx:
                        max_col = max(cells_by_idx.keys())
                        rows.append([cells_by_idx.get(i) for i in range(max_col + 1)])
            sheets_out[name] = rows
    return sheets_out


def read_workbook_sheets(xlsx_path: Path) -> Dict[str, List[List[Any]]]:
    """Read sheets from `.xlsx` using openpyxl if available, otherwise stdlib OOXML reader."""
    try:
        import openpyxl  # type: ignore

        wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
        try:
            out: Dict[str, List[List[Any]]] = {}
            for name in wb.sheetnames:
                ws = wb[name]
                out[name] = [list(row) for row in ws.iter_rows(values_only=True)]
            return out
        finally:
            wb.close()
    except ImportError:
        return _read_xlsx_via_stdlib(xlsx_path)


def _norm_header(raw: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


def _rows_to_dicts(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    headers = [_norm_header(h) for h in rows[0]]
    records: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if not any(cell is not None and str(cell).strip() != "" for cell in row):
            continue
        item: Dict[str, Any] = {}
        for idx, key in enumerate(headers):
            if not key:
                continue
            item[key] = row[idx] if idx < len(row) else None
        records.append(item)
    return records


def _pick(rec: Dict[str, Any], *aliases: str) -> Any:
    for alias in aliases:
        if alias in rec and rec[alias] is not None and str(rec[alias]).strip() != "":
            return rec[alias]
    return None


def _parse_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in _TRUTHY_STRINGS:
        return True
    if s in _FALSY_STRINGS:
        return False
    return default


def _parse_optional_year(val: Any) -> Optional[int]:
    if val is None:
        return None
    text = str(val).strip()
    if not text:
        return None
    m = re.search(r"\b(1[6-9]\d{2}|20\d{2}|2100)\b", text)
    if m:
        return int(m.group(1))
    try:
        iv = int(float(text))
        if 1600 <= iv <= 2100:
            return iv
    except ValueError:
        pass
    return None


def _normalize_house_id(raw: Any, is_reference: bool = False) -> str:
    if is_reference:
        return "REFERENCE"
    text = str(raw or "").strip().upper()
    if not text:
        return "FOUNDERS"
    if text in {"FOUNDERS", "FOUNDER", "ROOT", "FOUNDING"}:
        return "FOUNDERS"
    if text in {"REFERENCE", "REF", "HISTORICAL_REFERENCE"}:
        return "REFERENCE"
    digits = text.replace("HOUSE-", "").replace("HOUSE ", "").replace("HOUSE", "").strip()
    if digits.isdigit() and 1 <= int(digits) <= 12:
        return f"HOUSE-{int(digits):02d}"
    raise ValueError(f"Unsupported house_id value: {raw!r}")


def _normalize_rel_type(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text in {"parent", "parent_child", "parent-child", "father", "mother"}:
        return "parent"
    if text in {"spouse", "partner", "marriage", "married", "husband", "wife"}:
        return "spouse"
    raise ValueError(f"Unsupported relationship type: {raw!r} (expected 'parent' or 'spouse')")


def convert_workbook_to_seed_dict(xlsx_path: Path) -> Dict[str, Any]:
    """Parse, normalize, and validate an Excel workbook into the canonical seed payload."""
    sheets = read_workbook_sheets(xlsx_path)
    sheet_lookup = {k.strip().lower(): v for k, v in sheets.items()}

    if "people" not in sheet_lookup:
        raise ValueError(f"Workbook {xlsx_path} is missing required 'People' sheet.")
    if "relationships" not in sheet_lookup:
        raise ValueError(f"Workbook {xlsx_path} is missing required 'Relationships' sheet.")

    raw_people = _rows_to_dicts(sheet_lookup["people"])
    raw_rels = _rows_to_dicts(sheet_lookup["relationships"])

    people_out: List[Dict[str, Any]] = []
    seen_person_ids: set[str] = set()

    for idx, rec in enumerate(raw_people, start=2):
        pid = str(_pick(rec, "person_id", "personid", "id") or "").strip()
        if not pid:
            raise ValueError(f"People row {idx}: missing person_id")
        if pid in seen_person_ids:
            raise ValueError(f"People row {idx}: duplicate person_id '{pid}'")
        seen_person_ids.add(pid)

        raw_given = str(_pick(rec, "given_name", "givenname", "first_name", "firstname") or "").strip()
        raw_surname = str(_pick(rec, "surname", "last_name", "lastname", "family_name") or "").strip()
        raw_suffix = str(_pick(rec, "suffix", "name_suffix", "gen_suffix") or "").strip()
        clean_surname, clean_suffix = normalize_surname_and_suffix(raw_surname, raw_suffix)

        raw_full = str(_pick(rec, "full_name", "fullname", "display_name", "name") or "").strip()
        if not raw_full:
            raw_full = " ".join(part for part in (raw_given, clean_surname, clean_suffix) if part).strip()
        if not raw_full:
            raise ValueError(f"People row {idx} ({pid}): missing full_name")
        if not raw_given:
            raw_given = raw_full.split(" ")[0]

        nickname = str(_pick(rec, "nickname", "nick_name", "aka") or "").strip()
        is_ref = _parse_bool(_pick(rec, "is_reference_branch", "reference_branch", "reference"), default=False)
        house_raw = _pick(rec, "house_id", "house", "branch", "lineage_code")
        if str(house_raw or "").strip().upper() in {"REFERENCE", "REF"}:
            is_ref = True
        house_id = _normalize_house_id(house_raw, is_reference=is_ref)

        gen_raw = _pick(rec, "generation", "gen")
        generation = int(float(gen_raw)) if gen_raw is not None else 0

        birth_year = _parse_optional_year(_pick(rec, "birth_year", "birthyear", "born"))
        death_year = _parse_optional_year(_pick(rec, "death_year", "deathyear", "died"))
        is_deceased = _parse_bool(_pick(rec, "is_deceased", "deceased"), default=(death_year is not None))
        if death_year is not None:
            is_deceased = True

        bio_notes = str(_pick(rec, "bio_notes", "bionotes", "notes", "biography") or "").strip()
        source_tag = str(_pick(rec, "source_tag", "sourcetag", "source") or "EXCEL_IMPORT").strip()
        review_flag = str(_pick(rec, "review_flag", "reviewflag", "flag", "discrepancy_note") or "").strip()

        people_out.append(
            {
                "person_id": pid,
                "full_name": raw_full,
                "given_name": raw_given,
                "surname": clean_surname,
                "suffix": clean_suffix,
                "nickname": nickname,
                "house_id": house_id,
                "generation": generation,
                "is_deceased": is_deceased,
                "birth_year": birth_year,
                "death_year": death_year,
                "bio_notes": bio_notes,
                "source_tag": source_tag,
                "review_flag": review_flag,
                "is_reference_branch": is_ref,
            }
        )

    rels_out: List[Dict[str, Any]] = []
    seen_rel_ids: set[str] = set()
    broken_refs: List[str] = []

    for idx, rec in enumerate(raw_rels, start=2):
        rid = str(_pick(rec, "rel_id", "relid", "id") or f"R{idx - 1:05d}").strip()
        if rid in seen_rel_ids:
            raise ValueError(f"Relationships row {idx}: duplicate rel_id '{rid}'")
        seen_rel_ids.add(rid)

        rel_type = _normalize_rel_type(_pick(rec, "rel_type", "reltype", "type", "relationship_type"))
        person_a = str(_pick(rec, "person_a_id", "person_a", "persona_id", "parent_id", "from_id") or "").strip()
        person_b = str(_pick(rec, "person_b_id", "person_b", "personb_id", "child_id", "to_id") or "").strip()

        if person_a not in seen_person_ids:
            broken_refs.append(f"Row {idx} ({rid}): unknown person_a_id '{person_a}'")
        if person_b not in seen_person_ids:
            broken_refs.append(f"Row {idx} ({rid}): unknown person_b_id '{person_b}'")
        if person_a and person_a == person_b:
            broken_refs.append(f"Row {idx} ({rid}): self-referential edge '{person_a}'")

        rels_out.append(
            {
                "rel_id": rid,
                "rel_type": rel_type,
                "person_a_id": person_a,
                "person_b_id": person_b,
                "notes": str(_pick(rec, "notes", "note") or "").strip(),
                "source_tag": str(_pick(rec, "source_tag", "sourcetag", "source") or "EXCEL_IMPORT").strip(),
            }
        )

    if broken_refs:
        raise ValueError(
            f"Referential integrity check failed ({len(broken_refs)} broken ID reference(s)):\n"
            + "\n".join(broken_refs[:20])
        )

    people_out.sort(key=lambda item: item["person_id"])
    rels_out.sort(key=lambda item: item["rel_id"])

    return {
        "schema_version": "1.0.0",
        "title": "Carmichael — McCormick 12-House Family Tree Seed",
        "privacy_policy": "Living-member birth_year and contact metadata are stripped server-side on all public/member read endpoints.",
        "people": people_out,
        "relationships": rels_out,
    }


def import_excel_to_json(xlsx_path: Path, output_path: Path = DEFAULT_OUTPUT_PATH) -> Dict[str, Any]:
    """Convert an Excel workbook to deterministic `family_tree_seed.json`."""
    payload = convert_workbook_to_seed_dict(xlsx_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import normalized People & Relationships Excel sheets into deterministic family_tree_seed.json."
    )
    parser.add_argument("xlsx", type=Path, help="Path to source .xlsx workbook")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON seed path (default: {DEFAULT_OUTPUT_PATH})",
    )
    args = parser.parse_args(argv)
    payload = import_excel_to_json(args.xlsx, args.output)
    print(
        f"Imported {len(payload['people'])} people and {len(payload['relationships'])} relationships "
        f"(0 broken references) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
