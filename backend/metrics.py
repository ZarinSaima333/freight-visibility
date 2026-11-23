"""Shared definitions for metrics across the API and CLI."""

METRICS = '''
    count(*) AS count,
    count(*) FILTER (WHERE is_valid_delivery) AS valid_deliveries,
    count(*) FILTER (WHERE status = 'Delivered' AND NOT is_valid_delivery) AS delivered_excluded,
    round(100.0 * avg((delay_days <= %s)::int) FILTER (WHERE is_valid_delivery), 1) AS on_time_pct,
    round(avg(delay_days) FILTER (WHERE is_valid_delivery), 1) AS average_delay
'''


def lanes(conn, grace: int) -> list[dict]:
    return conn.execute(
        'SELECT trade_lane AS lane, ' + METRICS +
        ' FROM shipments GROUP BY trade_lane ORDER BY count DESC, lane', (grace,)
    ).fetchall()


def carriers(conn, grace: int) -> list[dict]:
    return conn.execute(
        'SELECT carrier, ' + METRICS +
        ' FROM shipments GROUP BY carrier ORDER BY count DESC, carrier', (grace,)
    ).fetchall()


def summary(conn, grace: int) -> dict:
    row = conn.execute('SELECT ' + METRICS + ''',
        round(coalesce(sum(weight_kg) FILTER (WHERE weight_ok), 0) / 1000, 3) AS total_weight_tonnes,
        count(*) FILTER (WHERE NOT weight_ok) AS weight_excluded,
        count(*) FILTER (WHERE status = 'In Transit') AS in_transit,
        count(*) FILTER (WHERE max_severity = 'ERROR') AS errors,
        count(*) FILTER (WHERE max_severity = 'WARNING') AS warnings
        FROM shipments
    ''', (grace,)).fetchone()
    row['unique_shipments'] = row.pop('count')
    row['top_lanes'] = [{'lane': lane['lane'], 'count': lane['count']} for lane in lanes(conn, grace)[:3]]
    return row
