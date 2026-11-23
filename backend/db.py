"""PostgreSQL storage and atomic snapshot ingestion."""

import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .cleaning import clean_rows, read_csv

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'shipments_2026H1.csv'
load_dotenv(ROOT / '.env')
logger = logging.getLogger(__name__)


def connect(*, readonly: bool = False) -> psycopg.Connection:
    url = (os.getenv('READONLY_DATABASE_URL') if readonly else None) or os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('Set DATABASE_URL to an empty PostgreSQL database before starting.')
    conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=5)
    if readonly:
        conn.read_only = True
    return conn


def ingest(conn: psycopg.Connection, content: bytes, filename: str, mode: str) -> dict:
    incoming = read_csv(content)
    # Serialize uploads and seed initialization across workers.
    conn.execute('SELECT pg_advisory_xact_lock(14213001)')
    batch = conn.execute(
        'INSERT INTO upload_batches (filename, raw_rows) VALUES (%s, %s) RETURNING id',
        (filename, len(incoming)),
    ).fetchone()['id']
    previous = []
    if mode == 'append':
        # Re-evaluate all active source versions, including previously dropped alternatives.
        previous = conn.execute('''
            SELECT id, batch_id, raw FROM shipments_raw
            WHERE id IN (
                SELECT raw_id FROM shipments
                UNION
                SELECT dropped_raw_id FROM removed_duplicates
                WHERE batch_id = (SELECT max(id) FROM upload_batches WHERE id < %s)
            )
            ORDER BY id
        ''', (batch,)).fetchall()
    new = [
        conn.execute('INSERT INTO shipments_raw (batch_id, raw) VALUES (%s, %s) RETURNING id, batch_id, raw',
                     (batch, Jsonb(raw))).fetchone()
        for raw in incoming
    ]
    shipments, duplicates, report = clean_rows(previous + new)
    conn.execute('DELETE FROM shipments')
    with conn.cursor() as cur:
        cur.executemany('''
            INSERT INTO shipments (
                shipment_id, mode, container_mode, carrier, origin_port, destination_port,
                trade_lane, shipper, consignee, etd, eta, atd, ata, weight_kg_raw, weight_kg,
                weight_ok, volume_cbm, status, delay_days, dep_delay_days, is_valid_delivery,
                max_severity, issues, upload_batch_id, raw_id, flags
            ) VALUES (
                %(shipment_id)s, %(mode)s, %(container_mode)s, %(carrier)s, %(origin_port)s,
                %(destination_port)s, %(trade_lane)s, %(shipper)s, %(consignee)s, %(etd)s, %(eta)s,
                %(atd)s, %(ata)s, %(weight_kg_raw)s, %(weight_kg)s, %(weight_ok)s, %(volume_cbm)s,
                %(status)s, %(delay_days)s, %(dep_delay_days)s, %(is_valid_delivery)s,
                %(max_severity)s, %(issues)s, %(upload_batch_id)s, %(raw_id)s, %(flags)s
            )
        ''', [{**row, 'flags': Jsonb(row['flags'])} for row in shipments])
        cur.executemany('''
            INSERT INTO removed_duplicates (batch_id, shipment_id, kept_raw_id, dropped_raw_id, reason)
            VALUES (%(batch_id)s, %(shipment_id)s, %(kept_raw_id)s, %(dropped_raw_id)s, %(reason)s)
        ''', [{**row, 'batch_id': batch} for row in duplicates])
    report.update(batch_id=batch, filename=filename, uploaded_rows=len(incoming), mode=mode)
    conn.execute('UPDATE upload_batches SET unique_shipments = %s, report = %s WHERE id = %s',
                 (report['unique_shipments'], Jsonb(report), batch))
    logger.info('Cleaning report: %s', report)
    return report


def initialize() -> None:
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(14213001)')
        conn.execute((ROOT / 'db' / 'init.sql').read_text())
        if SEED.exists() and not conn.execute('SELECT 1 FROM shipments LIMIT 1').fetchone():
            ingest(conn, SEED.read_bytes(), SEED.name, 'replace')
