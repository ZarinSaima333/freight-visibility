import React from 'react';
import { display, number } from './api';

export function Status({ state, children }) {
  if (state.loading) return <p className="state" role="status">Loading…</p>;
  if (state.error) return <p className="state error" role="alert">{state.error}</p>;
  return children(state.data);
}

export function Badge({ value, tone = value?.toLowerCase() }) {
  return <span className={`badge ${tone || ''}`}>{value}</span>;
}

export function Table({ columns, rows, rowKey, empty = 'No rows to display.' }) {
  if (!rows.length) return <p className="state">{empty}</p>;
  return <div className="table-wrap"><table>
    <thead><tr>{columns.map(([key, name]) => <th key={key} scope="col">{name}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={rowKey ? rowKey(row) : index}>
      {columns.map(([key, , render]) => <td key={key}>{render ? render(row[key], row) : display(row[key])}</td>)}
    </tr>)}</tbody>
  </table></div>;
}

export function Reconciliation({ report }) {
  const steps = [
    ['Raw rows', report.raw_rows],
    ['Duplicates removed', report.duplicates_removed],
    ['Unique shipments', report.unique_shipments],
    ['Valid deliveries', report.valid_deliveries],
  ];
  return <div className="funnel">{steps.map(([label, value]) => <div key={label}>
    <strong>{number(value)}</strong><span>{label}</span>
  </div>)}</div>;
}
