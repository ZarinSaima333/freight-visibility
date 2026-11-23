import React, { useState } from 'react';
import { Badge, Reconciliation, Status, Table } from './components';
import { useRequest } from './api';

export default function Quality({ revision, navigate }) {
  const state = useRequest('/api/data-quality', revision);
  const [severity, setSeverity] = useState('all');
  const [rule, setRule] = useState('all');
  return <Status state={state}>{({ latest, rules, flagged_rows: flagged }) => <>
    <section className="card">
      <div className="section-heading">
        <h2>Data reconciliation</h2>
        <a className="button" href="/api/data-quality/export">Download for operations</a>
      </div>
      {latest ? <>
        <p className="muted">{latest.filename} · {latest.report.mode === 'append' ? 'Combined active source rows' : 'Latest uploaded snapshot'}</p>
        <Reconciliation report={latest.report} />
        <p className="muted">{latest.report.exact_duplicates} exact duplicates and {latest.report.conflicting_duplicates} conflicting rows removed. {latest.report.delivered_excluded} deliveries and {latest.report.weight_excluded} weights excluded from their respective metrics.</p>
      </> : <p className="state">No upload has been recorded.</p>}
    </section>
    <section className="card">
      <h2>Issue types</h2>
      <p className="muted">Counts show affected shipments per rule. One shipment can trigger several rules.</p>
      <Table rows={[...rules].sort((a, b) => b.count - a.count)} rowKey={row => row.code} columns={[
        ['description', 'Rule'], ['severity', 'Severity', value => <Badge value={value} />], ['count', 'Shipments'],
      ]} />
    </section>
    <section className="card">
      <h2>Flagged shipments</h2>
      <div className="filters">
        <label>Severity <select value={severity} onChange={event => setSeverity(event.target.value)}>
          <option value="all">All severities</option><option value="ERROR">Error</option><option value="WARNING">Warning</option>
        </select></label>
        <label>Issue <select value={rule} onChange={event => setRule(event.target.value)}>
          <option value="all">All issues</option>{rules.filter(item => item.count).map(item =>
            <option key={item.code} value={item.code}>{item.description}</option>)}
        </select></label>
      </div>
      <Table rows={flagged.filter(row => (severity === 'all' || row.severity === severity) &&
        (rule === 'all' || row.flags.some(flag => flag.code === rule)))}
        rowKey={row => row.shipment_id} empty="No flagged shipments match these filters." columns={[
          ['shipment_id', 'Shipment ID', id => <button className="text-button" onClick={() => navigate(id)}>{id}</button>],
          ['severity', 'Severity', value => <Badge value={value} />], ['issues', 'Issues'],
        ]} />
    </section>
  </>}</Status>;
}
