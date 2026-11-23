import React, { useEffect, useState } from 'react';
import { Badge, Status, Table } from './components';
import { cities, display, laneName, useRequest } from './api';

const sourceFields = {
  shipment_id: 'Shipment ID', mode: 'Mode', container_mode: 'Container Mode',
  carrier: 'Carrier', origin_port: 'Origin Port', destination_port: 'Destination Port',
  shipper: 'Shipper', consignee: 'Consignee', etd: 'ETD', eta: 'ETA',
  atd: 'ATD', ata: 'ATA', weight_kg: 'Weight (KG)', volume_cbm: 'Volume (CBM)', status: 'Status',
};

function RawValue({ value }) {
  return value === '' ? <em>blank</em> : <code className="raw-value">{display(value)}</code>;
}

function Detail({ id, grace, revision, onClose }) {
  const state = useRequest(`/api/shipments/${encodeURIComponent(id)}`, revision);
  return <section className="card detail" aria-label="Shipment details">
    <div className="section-heading"><h2>{id}</h2><button className="secondary" onClick={onClose}>Close details</button></div>
    <Status state={state}>{row => <>
      <p>{laneName(row.trade_lane)}</p>
      <div className="badge-row">
        <Badge value={row.status} />
        <Badge value={row.max_severity} />
        {row.is_valid_delivery ? <Badge value={row.delay_days <= grace ? 'On time' : 'Late'} tone={row.delay_days <= grace ? 'ok' : 'error'} />
          : <Badge value={row.status === 'Delivered' ? 'Date metrics excluded' : 'Delivery timing unavailable'} />}
      </div>
      <dl className="detail-grid">
        {Object.entries(sourceFields).map(([key, label]) => {
          const value = row[key];
          const title = cities[value] && key.endsWith('_port') ? `${cities[value]} (${value})` : display(value);
          return <div key={key}><dt>{label}</dt><dd>{title}</dd></div>;
        })}
        <div><dt>Arrival delay (days)</dt><dd>{display(row.delay_days)}{row.delay_days != null && !row.is_valid_delivery ? ' (excluded)' : ''}</dd></div>
        <div><dt>Departure delay (days)</dt><dd>{display(row.dep_delay_days)}</dd></div>
        <div><dt>Source batch</dt><dd>{row.upload_batch_id}</dd></div>
      </dl>
      <h3>Data issues</h3>
      {row.flags.length ? <ul className="issue-list">{row.flags.map((flag, index) => <li key={index}>
        <Badge value={flag.severity} /> {flag.message}
        {!!flag.fields.length && <div className="muted">{flag.fields.map(field => <span className="raw-field" key={field}>
          {sourceFields[field]} <RawValue value={row.raw[sourceFields[field]]} />
        </span>)}</div>}
      </li>)}</ul> : <p className="muted">No issues found.</p>}
      {!!row.duplicates.length && <details>
        <summary>Compare duplicate source rows ({row.duplicates.length})</summary>
        <Table rows={[{ reason: 'Kept', raw: row.raw }, ...row.duplicates]}
          columns={ [['reason', 'Version'], ...Object.values(sourceFields).map(field =>
            [field, field, (_, item) => <RawValue value={item.raw[field]} />])] } />
      </details>}
      <details>
        <summary>Original uploaded values</summary>
        <dl className="detail-grid">{Object.entries(row.raw).map(([field, value]) =>
          <div key={field}><dt>{field}</dt><dd><RawValue value={value} /></dd></div>)}</dl>
      </details>
    </>}</Status>
  </section>;
}

export default function Shipments({ revision, grace, selected, setSelected }) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 200);
    return () => clearTimeout(timer);
  }, [query]);
  const state = useRequest(`/api/search?q=${encodeURIComponent(debounced)}`, revision);
  return <>
    <section className="card">
      <h2>Find a shipment</h2>
      <label className="field-label" htmlFor="shipment-search">Shipment ID, carrier, shipper or consignee</label>
      <input id="shipment-search" type="search" value={query} maxLength={200}
        onChange={event => setQuery(event.target.value)} placeholder="Search shipments…" />
    </section>
    {selected && <Detail id={selected} revision={revision} grace={grace} onClose={() => setSelected('')} />}
    <section className="card">
      <h2>Search results</h2>
      <Status state={state}>{rows => <Results rows={rows} select={setSelected} selected={selected} query={debounced} />}</Status>
    </section>
  </>;
}

function Results({ rows, select, selected, query }) {
  const [pagination, setPagination] = useState({ query, page: 0 });
  const current = pagination.query === query ? pagination.page : 0;
  const page = Math.min(current, Math.max(0, Math.ceil(rows.length / 25) - 1));
  const offset = page * 25;
  return <>
    {!!rows.length && <p className="muted">{rows.length} shipments found</p>}
    <Table rows={rows.slice(offset, offset + 25)} rowKey={row => row.shipment_id} empty="No matching shipments."
      columns={[
        ['shipment_id', 'Shipment ID', id => <button className="text-button" aria-pressed={id === selected} onClick={() => {
          select(id);
          document.querySelector('main')?.scrollIntoView({ block: 'start' });
        }}>{id}</button>],
        ['carrier', 'Carrier'], ['trade_lane', 'Trade lane', laneName], ['status', 'Status'],
        ['max_severity', 'Data quality', value => <Badge value={value} />],
      ]} />
    {rows.length > 25 && <div className="pagination">
      <button className="secondary" disabled={!page} onClick={() => setPagination({ query, page: page - 1 })}>Previous</button>
      <span>{offset + 1}–{Math.min(offset + 25, rows.length)} of {rows.length}</span>
      <button className="secondary" disabled={offset + 25 >= rows.length}
        onClick={() => setPagination({ query, page: page + 1 })}>Next</button>
    </div>}
  </>;
}
