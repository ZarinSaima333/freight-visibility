"""Freight metrics, shipment inspection, and CSV ingestion API."""

import csv
import io
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import metrics
from .chat import router as chat_router
from .cleaning import COLUMNS, RULES
from .db import connect, ingest, initialize

MAX_UPLOAD = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_logger = logging.getLogger('backend.db')
    db_logger.setLevel(logging.INFO)
    if not db_logger.handlers:
        for handler in logging.getLogger('uvicorn').handlers:
            db_logger.addHandler(handler)
    db_logger.propagate = not db_logger.handlers
    await run_in_threadpool(initialize)
    yield


app = FastAPI(title='Freight Visibility', lifespan=lifespan)
app.include_router(chat_router)
app.add_middleware(
    CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['GET', 'POST'], allow_headers=['Content-Type'],
)


@app.get('/api/summary')
def get_summary(grace: int = Query(0, ge=0, le=3)) -> dict:
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return metrics.summary(conn, grace)


@app.get('/api/lanes')
def get_lanes(grace: int = Query(0, ge=0, le=3)) -> list[dict]:
    with connect() as conn:
        return metrics.lanes(conn, grace)


@app.get('/api/carriers')
def get_carriers(grace: int = Query(0, ge=0, le=3)) -> list[dict]:
    with connect() as conn:
        return metrics.carriers(conn, grace)


@app.get('/api/top-delayed')
def top_delayed(limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    with connect() as conn:
        return conn.execute('''
            SELECT shipment_id, carrier, trade_lane, eta, ata, delay_days
            FROM shipments WHERE is_valid_delivery AND delay_days > 0
            ORDER BY delay_days DESC, shipment_id LIMIT %s
        ''', (limit,)).fetchall()


@app.get('/api/search')
def search(q: str = Query('', max_length=200)) -> list[dict]:
    with connect() as conn:
        return conn.execute('''
            SELECT shipment_id, mode, carrier, shipper, consignee, trade_lane, status, max_severity
            FROM shipments
            WHERE strpos(lower(shipment_id), lower(%(q)s)) > 0
               OR strpos(lower(carrier), lower(%(q)s)) > 0
               OR strpos(lower(shipper), lower(%(q)s)) > 0
               OR strpos(lower(consignee), lower(%(q)s)) > 0
            ORDER BY shipment_id
        ''', {'q': q.strip()}).fetchall()


@app.get('/api/shipments/{shipment_id}')
def shipment_detail(shipment_id: str) -> dict:
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        row = conn.execute('''
            SELECT s.*, r.raw FROM shipments s JOIN shipments_raw r ON r.id = s.raw_id
            WHERE s.shipment_id = %s
        ''', (shipment_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Shipment not found.')
        row['duplicates'] = conn.execute('''
            SELECT d.reason, r.raw FROM removed_duplicates d
            JOIN shipments_raw r ON r.id = d.dropped_raw_id
            WHERE d.shipment_id = %s AND d.batch_id = (SELECT max(id) FROM upload_batches)
            ORDER BY d.dropped_raw_id
        ''', (shipment_id,)).fetchall()
        return row


def flagged_rows(conn) -> list[dict]:
    return conn.execute('''
        SELECT s.shipment_id, s.max_severity AS severity, s.issues, s.flags, r.raw
        FROM shipments s JOIN shipments_raw r ON r.id = s.raw_id
        WHERE s.max_severity <> 'OK'
        ORDER BY CASE WHEN s.max_severity = 'ERROR' THEN 0 ELSE 1 END, s.shipment_id
    ''').fetchall()


@app.get('/api/data-quality')
def data_quality() -> dict:
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        batch = conn.execute('SELECT * FROM upload_batches ORDER BY id DESC LIMIT 1').fetchone()
        report = batch['report'] if batch else {}
        counts = report.get('issue_counts', {})
        rules = [dict(code=code, severity=severity, description=description, count=counts.get(code, 0))
                 for code, (severity, description) in RULES.items()]
        return dict(latest=batch, rules=rules, flagged_rows=flagged_rows(conn))


def spreadsheet_cell(value: str) -> str:
    """Protect spreadsheet opens while retaining the source string in the audit store."""
    if value.startswith(('\t', '\r', '\n')) or value.lstrip().startswith(('=', '+', '-', '@')):
        try:
            if value and float(value) < 0:
                return value
        except ValueError:
            pass
        return "'" + value
    return value


@app.get('/api/data-quality/export')
def export_data_quality() -> Response:
    with connect() as conn:
        rows = flagged_rows(conn)
        conflicts = conn.execute('''
            SELECT d.shipment_id, r.raw FROM removed_duplicates d
            JOIN shipments_raw r ON r.id = d.dropped_raw_id
            WHERE d.reason = 'conflicting' AND d.batch_id = (SELECT max(id) FROM upload_batches)
            ORDER BY d.dropped_raw_id
        ''').fetchall()
    alternatives = {}
    for conflict in conflicts:
        alternatives.setdefault(conflict['shipment_id'], []).append(conflict['raw'])
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['shipment_id', 'severity', 'issues', 'source_version', *COLUMNS])
    for row in rows:
        sources = [('kept', row['raw']), *[('conflicting', raw) for raw in alternatives.get(row['shipment_id'], [])]]
        for version, raw in sources:
            writer.writerow([spreadsheet_cell(row['shipment_id']), row['severity'], row['issues'], version,
                             *[spreadsheet_cell(raw[column]) for column in COLUMNS]])
    return Response(stream.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="freight-data-quality.csv"'})


def save_upload(content: bytes, filename: str, mode: str) -> dict:
    with connect() as conn:
        return ingest(conn, content, filename, mode)


@app.post('/api/upload')
async def upload(file: UploadFile = File(...), mode: Literal['replace', 'append'] = 'replace') -> dict:
    filename = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    if not filename.lower().endswith('.csv'):
        raise HTTPException(400, 'Choose a .csv file.')
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, 'The file exceeds the 10 MB limit.')
    try:
        return await run_in_threadpool(save_upload, content, filename, mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
