"""Parse source rows without losing evidence or conflating KPI eligibility."""

import csv
import io
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import groupby

import pandas as pd

COLUMNS = dict(zip(
    ('Shipment ID,Mode,Container Mode,Carrier,Origin Port,Destination Port,'
     'Shipper,Consignee,ETD,ETA,ATD,ATA,Weight (KG),Volume (CBM),Status').split(','),
    ('shipment_id mode container_mode carrier origin_port destination_port shipper '
     'consignee etd eta atd ata weight_kg volume_cbm status').split(),
))
DATE_FIELDS = ('etd', 'eta', 'atd', 'ata')
ALIASES = {'CHATTOGRAM': 'BDCGP', 'CGP': 'BDCGP'}
RULES = {
    'date_dmy': ('WARNING', 'date read as D/M/Y'),
    'duplicate_conflict': ('WARNING', 'conflicting duplicate, verify'),
    'missing_consignee': ('WARNING', 'Missing consignee'),
    'invalid_date': ('ERROR', 'Date could not be parsed'),
    'date_window': ('ERROR', 'Date outside December 2025 through December 2026'),
    'actual_order': ('ERROR', 'ATA before ATD'),
    'planned_order': ('ERROR', 'ETA before ETD'),
    'missing_ata': ('ERROR', 'Delivered shipment has no ATA'),
    'missing_eta': ('ERROR', 'Delivered shipment has no ETA'),
    'unexpected_ata': ('ERROR', 'In Transit shipment has an ATA'),
    'suspect_delay': ('ERROR', 'Delay is above 60 or below −30 days'),
    'negative_weight': ('ERROR', 'Negative weight'),
    'zero_weight': ('ERROR', 'Zero weight'),
    'high_weight': ('ERROR', 'Weight exceeds 100,000 kg'),
    'invalid_weight': ('ERROR', 'Weight is missing or nonnumeric'),
    'invalid_volume': ('ERROR', 'Volume is nonnumeric'),
    'invalid_status': ('ERROR', 'Status must be Delivered or In Transit'),
}


def read_csv(content: bytes) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline=''), strict=True)
        if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS) or len(reader.fieldnames) != len(COLUMNS):
            raise ValueError('Expected CSV columns: ' + ', '.join(COLUMNS))
        rows = []
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f'CSV record ending on line {reader.line_num} has the wrong number of fields.')
            if any('\x00' in value for value in row.values()):
                raise ValueError('CSV contains a NUL character.')
            if not row['Shipment ID'].strip():
                raise ValueError(f'Missing Shipment ID on line {reader.line_num}.')
            rows.append(row)
    except UnicodeError as exc:
        raise ValueError('Save the CSV as UTF-8 and try again.') from exc
    except csv.Error as exc:
        raise ValueError(f'Malformed CSV: {exc}') from exc
    if not rows:
        raise ValueError('CSV has no shipment rows.')
    return rows


def parse_date(value: str) -> tuple[date | None, bool]:
    if not value:
        return None, False
    if re.fullmatch(r'\d{1,2}-[A-Za-z]{3}-\d{2}', value):
        return datetime.strptime(value, '%d-%b-%y').date(), False
    if not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', value):
        raise ValueError('Unrecognized date format')
    first, second, year = map(int, value.split('/'))
    if first > 12:
        return date(year, second, first), True
    return date(year, first, second), False


def numeric(value: str) -> Decimal | None:
    try:
        number = Decimal(value)
        # Bound precision to PostgreSQL NUMERIC's representable range.
        if number.is_finite() and number.adjusted() < 131072 and number.as_tuple().exponent >= -16383:
            return number
    except InvalidOperation:
        pass
    return None


def normalise(rows: list[dict]) -> tuple[list[dict], dict]:
    source = pd.DataFrame([row['raw'] for row in rows], columns=list(COLUMNS))
    trimmed = source.apply(lambda column: column.str.strip())
    counts = {'trimmed_fields': int(source.ne(trimmed).sum().sum())}
    for port in ('Origin Port', 'Destination Port'):
        upper = trimmed[port].str.upper()
        canonical = upper.replace(ALIASES)
        counts['uppercased_ports'] = counts.get('uppercased_ports', 0) + int(upper.ne(trimmed[port]).sum())
        counts['port_aliases'] = counts.get('port_aliases', 0) + int(upper.ne(canonical).sum())
        trimmed[port] = canonical
    return trimmed.rename(columns=COLUMNS).to_dict('records'), counts


def difference(end: date | None, start: date | None) -> int | None:
    return (end - start).days if end and start else None


def clean_shipment(values: dict, conflict: bool) -> tuple[dict, list[dict]]:
    shipment = values.copy()
    flags = []

    def flag(code: str, *fields: str) -> None:
        severity, message = RULES[code]
        flags.append(dict(code=code, severity=severity, message=message, fields=fields))

    if conflict:
        flag('duplicate_conflict')
    if not values['consignee']:
        flag('missing_consignee', 'consignee')
        shipment['consignee'] = 'Unknown'

    for field in DATE_FIELDS:
        try:
            parsed, fallback = parse_date(values[field])
        except ValueError:
            parsed, fallback = None, False
            flag('invalid_date', field)
        if fallback:
            flag('date_dmy', field)
        if parsed and not date(2025, 12, 1) <= parsed <= date(2026, 12, 31):
            flag('date_window', field)
        shipment[field] = parsed

    etd, eta, atd, ata = (shipment[field] for field in DATE_FIELDS)
    if ata and atd and ata < atd:
        flag('actual_order', 'ata', 'atd')
    if eta and etd and eta < etd:
        flag('planned_order', 'eta', 'etd')
    if values['status'] == 'Delivered':
        if not values['ata']:
            flag('missing_ata', 'ata', 'status')
        if not values['eta']:
            flag('missing_eta', 'eta', 'status')
    elif values['status'] == 'In Transit':
        if values['ata']:
            flag('unexpected_ata', 'ata', 'status')
    else:
        flag('invalid_status', 'status')

    delay = difference(ata, eta)
    if delay is not None and (delay > 60 or delay < -30):
        flag('suspect_delay', 'ata', 'eta')
    valid_delivery = values['status'] == 'Delivered' and delay is not None and all(
        issue['severity'] != 'ERROR' for issue in flags
    )
    weight = numeric(values['weight_kg'])
    if weight is None:
        flag('invalid_weight', 'weight_kg')
    elif weight < 0:
        flag('negative_weight', 'weight_kg')
    elif weight == 0:
        flag('zero_weight', 'weight_kg')
    elif weight > 100000:
        flag('high_weight', 'weight_kg')
    weight_ok = weight is not None and 0 < weight <= 100000

    volume = numeric(values['volume_cbm'])
    if volume is None and values['volume_cbm']:
        flag('invalid_volume', 'volume_cbm')
    shipment.update(
        trade_lane=f"{values['origin_port']} -> {values['destination_port']}",
        delay_days=delay, dep_delay_days=difference(atd, etd),
        is_valid_delivery=valid_delivery, weight_kg_raw=weight,
        weight_kg=weight if weight_ok else None, weight_ok=weight_ok, volume_cbm=volume,
        max_severity=max((item['severity'] for item in flags), key=('OK', 'WARNING', 'ERROR').index, default='OK'),
        issues='; '.join(item['message'] + (f" ({', '.join(item['fields'])})" if item['fields'] else '') for item in flags),
    )
    return shipment, flags


def clean_rows(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    normalised, counts = normalise(rows)
    records = sorted(zip(rows, normalised), key=lambda pair: pair[1]['shipment_id'])
    shipments, duplicates = [], []
    issue_counts = Counter()
    for shipment_id, group in groupby(records, key=lambda pair: pair[1]['shipment_id']):
        ranked = sorted(group, key=lambda pair: (
            pair[1]['status'] == 'Delivered',
            sum(bool(value) for value in pair[1].values()),
            pair[0]['batch_id'],
        ), reverse=True)
        source, values = ranked[0]
        conflict = False
        seen = {tuple(values.values())}
        for dropped, alternate in ranked[1:]:
            signature = tuple(alternate.values())
            exact = signature in seen
            seen.add(signature)
            conflict |= not exact
            duplicates.append(dict(shipment_id=shipment_id, kept_raw_id=source['id'],
                                   dropped_raw_id=dropped['id'], reason='exact' if exact else 'conflicting'))
        shipment, flags = clean_shipment(values, conflict)
        shipment.update(raw_id=source['id'], upload_batch_id=source['batch_id'], flags=flags)
        shipments.append(shipment)
        issue_counts.update({item['code'] for item in flags})
    report = dict(raw_rows=len(rows), unique_shipments=len(shipments),
                  duplicates_removed=len(duplicates),
                  exact_duplicates=sum(row['reason'] == 'exact' for row in duplicates),
                  conflicting_duplicates=sum(row['reason'] == 'conflicting' for row in duplicates),
                  valid_deliveries=sum(row['is_valid_delivery'] for row in shipments),
                  delivered_excluded=sum(row['status'] == 'Delivered' and not row['is_valid_delivery'] for row in shipments),
                  weight_excluded=sum(not row['weight_ok'] for row in shipments),
                  issue_counts=dict(issue_counts), normalisations=counts,
                  errors=sum(row['max_severity'] == 'ERROR' for row in shipments),
                  warnings=sum(row['max_severity'] == 'WARNING' for row in shipments))
    return shipments, duplicates, report
