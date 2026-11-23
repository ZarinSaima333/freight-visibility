"""Constrain generated SQL to a small, read-only PostgreSQL dialect."""

from pglast import ast, parse_sql
from pglast.enums import LimitOption
from pglast.parser import ParseError
from pglast.stream import RawStream
from psycopg.rows import tuple_row

from .db import connect

ALLOWED_NODES = {
    'SelectStmt', 'RangeVar', 'Alias', 'ResTarget', 'ColumnRef', 'A_Star',
    'A_Const', 'String', 'Integer', 'Float', 'Boolean', 'A_Expr', 'BoolExpr',
    'NullTest', 'BooleanTest', 'SortBy', 'FuncCall', 'TypeCast', 'TypeName',
    'WithClause', 'CommonTableExpr', 'RangeSubselect', 'CaseExpr', 'CaseWhen',
    'CoalesceExpr',
}
FUNCTIONS = {'count', 'sum', 'avg', 'min', 'max', 'round', 'abs', 'lower', 'upper',
             'length', 'date_trunc', 'date_part'}
OPERATORS = {'=', '<>', '!=', '>', '<', '>=', '<=', '+', '-', '*', '/', '%',
             '~~', '!~~', '~~*', '!~~*'}
CASTS = {'int2', 'int4', 'int8', 'numeric', 'float4', 'float8', 'text', 'date', 'bool'}


class UnsafeQuery(ValueError):
    pass


def names(nodes) -> tuple[str, ...]:
    return tuple(node.sval for node in nodes or ())


def validate_node(node, ctes: frozenset[str]) -> None:
    if isinstance(node, (tuple, list)):
        for item in node:
            validate_node(item, ctes)
        return
    if not isinstance(node, ast.Node):
        return
    if type(node).__name__ not in ALLOWED_NODES:
        raise UnsafeQuery('Use a plain SELECT with ordinary expressions on shipments.')
    if isinstance(node, ast.SelectStmt):
        if node.intoClause or node.lockingClause or node.valuesLists:
            raise UnsafeQuery('Use a read-only SELECT without row locks or SELECT INTO.')
        if node.withClause:
            if node.withClause.recursive:
                raise UnsafeQuery('Recursive queries are unavailable.')
            for cte in node.withClause.ctes:
                if cte.ctename == 'shipments' or cte.ctename in ctes:
                    raise UnsafeQuery('Use an unambiguous CTE name.')
                if not isinstance(cte.ctequery, ast.SelectStmt) or cte.search_clause or cte.cycle_clause:
                    raise UnsafeQuery('CTEs must contain plain SELECT queries.')
                validate_node(cte.ctequery, ctes)
                ctes = ctes | {cte.ctename}
    if isinstance(node, ast.RangeVar):
        if node.catalogname or node.schemaname not in (None, 'public'):
            raise UnsafeQuery('Only the shipments table is available.')
        if node.relname == 'shipments':
            node.schemaname = 'public'
            node.inh = False
        elif node.schemaname or node.relname not in ctes:
            raise UnsafeQuery('Only the shipments table is available.')
    if isinstance(node, ast.FuncCall):
        name = names(node.funcname)
        if len(name) != 1 or name[0] not in FUNCTIONS:
            raise UnsafeQuery('Use only the supported PostgreSQL functions.')
        node.funcname = (ast.String(sval='pg_catalog'), *node.funcname)
    if isinstance(node, ast.A_Expr):
        operator = names(node.name)
        if operator and (len(operator) != 1 or operator[0] not in OPERATORS):
            raise UnsafeQuery('Use ordinary arithmetic and comparison operators.')
    if isinstance(node, ast.SortBy) and node.useOp:
        raise UnsafeQuery('Use ordinary sort directions.')
    if isinstance(node, ast.TypeName):
        name = names(node.names)
        if not name or name[-1] not in CASTS or name[:-1] not in ((), ('pg_catalog',)) or node.setof or node.arrayBounds:
            raise UnsafeQuery('Use simple built-in data types.')
        node.names = (ast.String(sval='pg_catalog'), ast.String(sval=name[-1]))
    for key in node:
        if key != 'withClause':
            validate_node(getattr(node, key), ctes)


def validate_sql(sql: str) -> str:
    if len(sql) > 10000:
        raise UnsafeQuery('The query is too long.')
    try:
        statements = parse_sql(sql)
    except ParseError as exc:
        raise UnsafeQuery('Return a syntactically valid PostgreSQL SELECT.') from exc
    if len(statements) != 1 or not isinstance(statements[0].stmt, ast.SelectStmt):
        raise UnsafeQuery('Return exactly one SELECT.')
    query = statements[0].stmt
    validate_node(query, frozenset())
    limit = query.limitCount
    if not (isinstance(limit, ast.A_Const) and isinstance(limit.val, ast.Integer)
            and 0 <= limit.val.ival <= 100 and query.limitOption == LimitOption.LIMIT_OPTION_COUNT):
        query.limitCount = ast.A_Const(val=ast.Integer(ival=100))
        query.limitOption = LimitOption.LIMIT_OPTION_COUNT
    return RawStream()(query)


def run_query(sql: str) -> tuple[list[str], list[list]]:
    # The validator is also used for the mock and corrected queries.
    with connect(readonly=True) as conn:
        conn.execute("SET LOCAL statement_timeout = '5s'")
        conn.execute('SET LOCAL search_path TO pg_catalog')
        with conn.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(sql)
            columns = [column.name for column in cursor.description]
            rows = [list(row) for row in cursor.fetchmany(100)]
    return columns, rows
