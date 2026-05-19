#!/usr/bin/env python3
"""Dump every table/view in the Altium MSSQL library to one CSV per object.

Each base table or view becomes one ``<TableName>.csv`` inside ``--out`` (default
``csv/``). CSVs are written in RFC 4180 form (UTF-8, CRLF line ends, all fields
quoted, embedded quotes doubled) so they round-trip cleanly through Excel,
LibreOffice, pandas, etc. A leading ``_index.csv`` lists schema, original name,
type and row count for every dumped object.

Connection parameters are read from environment variables:

    MSSQL_HOST       e.g. db.altiumlibrary.com
    MSSQL_PORT       e.g. 1433  (optional, default 1433)
    MSSQL_USER       SQL login
    MSSQL_PASSWORD   SQL password
    MSSQL_DATABASE   e.g. altium_library
    MSSQL_DRIVER     ODBC driver name (optional, auto-detected)
    CSV_OUT_DIR      output directory (optional, default csv)
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

import pyodbc

# Reserved on Windows + characters that are awkward in shells.
_BAD_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _pick_driver() -> str:
    explicit = os.environ.get("MSSQL_DRIVER")
    if explicit:
        return explicit
    candidates = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "FreeTDS",
    ]
    installed = {d.strip() for d in pyodbc.drivers()}
    for name in candidates:
        if name in installed:
            return name
    if installed:
        return next(iter(installed))
    raise RuntimeError(
        "No ODBC driver found. Install msodbcsql18 (Linux/macOS) or set MSSQL_DRIVER."
    )


def _connect() -> pyodbc.Connection:
    host = os.environ["MSSQL_HOST"]
    port = os.environ.get("MSSQL_PORT", "1433")
    user = os.environ["MSSQL_USER"]
    password = os.environ["MSSQL_PASSWORD"]
    database = os.environ["MSSQL_DATABASE"]
    driver = _pick_driver()

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={user};PWD={password};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    print(f"Connecting via '{driver}' to {host}:{port}/{database} as {user}", flush=True)
    return pyodbc.connect(conn_str)


def _safe_filename(name: str, used: set[str]) -> str:
    base = _BAD_FS_CHARS.sub("_", name).strip().strip(".") or "table"
    candidate = base
    i = 2
    while candidate.lower() in used:
        candidate = f"{base}_{i:02d}"
        i += 1
    used.add(candidate.lower())
    return candidate


def _cell(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def main() -> int:
    out_dir = Path(os.environ.get("CSV_OUT_DIR", "csv"))
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW') "
            "ORDER BY TABLE_NAME"
        )
        objects = [(r[0], r[1], r[2]) for r in cursor.fetchall()]
        print(f"Found {len(objects)} tables/views", flush=True)

        used: set[str] = {"_index"}
        index_rows: list[tuple[str, str, str, str, int]] = []

        for i, (schema, name, obj_type) in enumerate(objects, 1):
            fname = _safe_filename(name, used)
            qualified = f"[{schema}].[{name}]" if schema else f"[{name}]"
            print(f"[{i:>3}/{len(objects)}] {name} -> {fname}.csv", flush=True)

            cursor.execute(f"SELECT * FROM {qualified}")
            columns = [c[0] for c in cursor.description]

            path = out_dir / f"{fname}.csv"
            row_count = 0
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(
                    fh,
                    dialect="excel",
                    quoting=csv.QUOTE_ALL,
                    lineterminator="\r\n",
                )
                writer.writerow(columns)
                for row in cursor:
                    writer.writerow([_cell(v) for v in row])
                    row_count += 1
            index_rows.append((fname, schema or "", name, obj_type, row_count))

        index_path = out_dir / "_index.csv"
        with index_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(
                fh,
                dialect="excel",
                quoting=csv.QUOTE_ALL,
                lineterminator="\r\n",
            )
            writer.writerow(["File", "Schema", "Object", "Type", "Rows"])
            writer.writerows(index_rows)

        total = sum(r[4] for r in index_rows)
        print(f"Wrote {len(index_rows)} CSVs, {total} rows total, into {out_dir}/", flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
