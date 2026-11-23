import pytest

from backend.chat_sql import UnsafeQuery, validate_sql
from backend.llm import EXAMPLES, ISSUES_SQL, mock_sql


@pytest.mark.parametrize('question,sql', EXAMPLES)
def test_example_queries(question, sql):
    assert mock_sql(question) == sql
    assert 'public.shipments' in validate_sql(sql)


def test_limit_and_cte():
    sql = validate_sql('WITH data AS (SELECT shipment_id FROM shipments) SELECT shipment_id FROM data')
    assert sql.endswith('LIMIT 100')
    assert validate_sql(ISSUES_SQL).endswith('LIMIT 100')
    assert validate_sql('SELECT * FROM shipments LIMIT 200').endswith('LIMIT 100')


@pytest.mark.parametrize('sql', [
    'SELECT * FROM upload_batches',
    'SELECT * FROM shipments; SELECT * FROM shipments',
    'SELECT * INTO another_table FROM shipments',
    'SELECT * FROM shipments FOR UPDATE',
    'WITH changed AS (DELETE FROM shipments RETURNING *) SELECT * FROM changed',
    'SELECT pg_sleep(10) FROM shipments',
    'SELECT * FROM pg_catalog.pg_class',
    'SELECT * FROM other.shipments',
])
def test_rejects_queries_outside_allowed_read_only_dialect(sql):
    with pytest.raises(UnsafeQuery):
        validate_sql(sql)
