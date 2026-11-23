from datetime import date

import pytest

from backend.cleaning import clean_rows, parse_date, read_csv
from backend.db import SEED


@pytest.fixture(scope='module')
def seed():
    rows = read_csv(SEED.read_bytes())
    return clean_rows([dict(id=i, batch_id=1, raw=row) for i, row in enumerate(rows)])


def test_shipment_ids_unique_and_duplicates_auditable(seed):
    shipments, duplicates, report = seed
    assert len(shipments) == len({row['shipment_id'] for row in shipments})
    assert len(shipments) + len(duplicates) == report['raw_rows']
    assert all(row['kept_raw_id'] != row['dropped_raw_id'] for row in duplicates)


def test_ports_normalized(seed):
    for row in seed[0]:
        for port in (row['origin_port'], row['destination_port']):
            assert port == port.strip().upper()
            assert port not in {'CGP', 'CHATTOGRAM'}


@pytest.mark.parametrize(('raw', 'expected', 'fallback'), [
    ('2/8/2026', date(2026, 2, 8), False),
    ('8-Feb-26', date(2026, 2, 8), False),
    ('17/02/2026', date(2026, 2, 17), True),
])
def test_date_parsing(raw, expected, fallback):
    assert parse_date(raw) == (expected, fallback)


def test_metric_exclusion_is_independent(seed):
    shipments, _, report = seed
    assert any(row['is_valid_delivery'] and not row['weight_ok'] for row in shipments)
    assert any(row['status'] == 'Delivered' and not row['is_valid_delivery'] and row['weight_ok'] for row in shipments)
    assert all(row['weight_ok'] == (row['weight_kg'] is not None) for row in shipments)
    assert report['weight_excluded'] == sum(not row['weight_ok'] for row in shipments)


def test_valid_delivery_order_and_on_time(seed):
    valid = [row for row in seed[0] if row['is_valid_delivery']]
    assert valid
    assert all(row['atd'] is None or row['ata'] >= row['atd'] for row in valid)
    assert all(row['eta'] and row['ata'] for row in valid)
    assert 0 <= 100 * sum(row['delay_days'] <= 0 for row in valid) / len(valid) <= 100
