import React, { useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge, Status, Table } from './components';
import { laneName, number, percent, useRequest } from './api';

const metricColumns = [
  ['count', 'Shipments', value => number(value)],
  ['on_time_pct', 'On-time', percent],
  ['valid_deliveries', 'Valid deliveries'],
  ['delivered_excluded', 'Date exclusions'],
  ['average_delay', 'Avg delay (days)'],
];

function Kpi({ label, value, detail }) {
  return <div className="card kpi"><h2>{label}</h2><strong>{value}</strong><p>{detail}</p></div>;
}

export default function Dashboard({ grace, setGrace, revision, navigate }) {
  const [seeAll, setSeeAll] = useState(false);
  const summary = useRequest(`/api/summary?grace=${grace}`, revision);
  const lanes = useRequest(`/api/lanes?grace=${grace}`, revision);
  const delayed = useRequest('/api/top-delayed', revision);
  const carriers = useRequest(`/api/carriers?grace=${grace}`, revision);
  const data = summary.data;
  const carrierRows = carriers.data || [];
  const worst = [...carrierRows].filter(row => row.average_delay != null)
    .sort((a, b) => Number(b.average_delay) - Number(a.average_delay))[0];
  const biggest = data?.top_lanes[0];

  return <>
    <Status state={summary}>{result => <>
      <div className="headline">
        <Kpi label="Total unique shipments" value={number(result.unique_shipments)}
          detail="0 exclusions after deduplication" />
        <Kpi label="On-time delivery" value={percent(result.on_time_pct)}
          detail={`${number(result.valid_deliveries)} valid deliveries · ${number(result.delivered_excluded)} excluded`} />
        <Kpi label="Total weight" value={<>{number(result.total_weight_tonnes, 1)} <small>t</small></>}
          detail={`${number(result.weight_excluded)} shipments excluded for bad weight`} />
      </div>
      <section className="card top-lanes">
        <h2>Top 3 trade lanes</h2>
        {result.top_lanes.length ? <ol>{result.top_lanes.map(lane => <li key={lane.lane}>
          <span>{laneName(lane.lane)}</span><strong>{number(lane.count)}</strong>
        </li>)}</ol> : <p className="state">No lanes available.</p>}
      </section>
      <div className="quality-banner">
        <div><strong>{number(result.errors + result.warnings)} shipments have data issues</strong>
          <p>{result.errors} errors · {result.warnings} warnings. Excluded from metrics where wrong.</p></div>
        <a href="#quality">View and download for operations</a>
      </div>
    </>}</Status>

    <div className="grace-row">
      <label htmlFor="grace">On-time grace period</label>
      <select id="grace" value={grace} onChange={event => setGrace(Number(event.target.value))}>
        {[0, 1, 2, 3].map(days => <option key={days} value={days}>{days} {days === 1 ? 'day' : 'days'}</option>)}
      </select>
    </div>

    <section className="card">
      <div className="section-heading"><h2>Shipments per trade lane</h2>
        <button className="secondary" onClick={() => setSeeAll(value => !value)} aria-expanded={seeAll}>
          {seeAll ? 'Hide lane table' : 'See all lanes'}
        </button></div>
      <Status state={lanes}>{rows => rows.length ? <>
        <p className="muted">Top {Math.min(rows.length, 10)} lanes by shipment count</p>
        <div className="chart" role="img" aria-label={rows.slice(0, 10).map(row => `${laneName(row.lane)}: ${row.count}`).join(', ')}>
          <ResponsiveContainer width="100%" height={Math.min(rows.length, 10) * 36 + 32}>
            <BarChart layout="vertical" data={rows.slice(0, 10).map(row => ({ ...row, label: laneName(row.lane) }))}
              margin={{ top: 8, right: 18, left: 4, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="3 4" />
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} tick={{fill: 'var(--muted)'}} />
              <YAxis type="category" dataKey="label" width={235} tickLine={false} axisLine={false} tick={{fontSize: 13, fill: 'var(--ink)'}} />
              <Tooltip cursor={{ fill: '#eee6d8' }} />
              <Bar name="Shipments" dataKey="count" fill="var(--primary)" radius={[0, 5, 5, 0]} barSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        {seeAll && <Table rows={rows} rowKey={row => row.lane}
          columns={ [['lane', 'Trade lane', laneName], ...metricColumns] } />}
      </> : <p className="state">No shipments to chart.</p>}</Status>
    </section>

    <section className="card">
      <h2>Top 10 most delayed shipments</h2>
      <p className="muted">{data ? `Excludes ${data.delivered_excluded} shipments with unreliable dates.` : 'Valid deliveries only.'}</p>
      <Status state={delayed}>{rows => <Table rows={rows} rowKey={row => row.shipment_id} empty="No delayed deliveries with reliable dates."
        columns={[
          ['shipment_id', 'Shipment ID', id => <button className="text-button" onClick={() => navigate(id)}>{id}</button>],
          ['carrier', 'Carrier'], ['trade_lane', 'Trade lane', laneName], ['eta', 'ETA'], ['ata', 'ATA'],
          ['delay_days', 'Delay', days => <Badge value={`+${days} d`} tone="error" />],
        ]} />}</Status>
    </section>

    <section className="card">
      <h2>Carrier scorecard</h2>
      <Status state={carriers}>{rows => <Table rows={rows} rowKey={row => row.carrier}
        columns={ [['carrier', 'Carrier'], ...metricColumns] } />}</Status>
    </section>
    <section className="card">
      <h2>Operational insights</h2>
      <Status state={summary}>{result => result.unique_shipments ? <ul className="insights">
        {worst && <li>{worst.carrier || 'Unknown carrier'} has the highest average delay at {number(worst.average_delay, 1)} days across {worst.valid_deliveries} valid deliveries.</li>}
        {biggest && <li>{laneName(biggest.lane)} accounts for {percent(100 * biggest.count / result.unique_shipments)} of shipments.</li>}
        <li>{number(result.in_transit)} shipments are recorded as in transit.</li>
        {result.average_delay != null && <li>The average arrival delay across valid deliveries is {number(result.average_delay, 1)} days.</li>}
      </ul> : <p className="state">Upload shipments to generate insights.</p>}</Status>
    </section>
    <section className="card assumptions">
      <h2>Assumptions</h2>
      <ul className="insights">
        <li>On time means ATA is on or before ETA plus the selected grace period.</li>
        <li>On-time performance uses Delivered shipments with an ETA, an ATA and no date errors.</li>
        <li>A trade lane runs from the origin port to the destination port.</li>
        <li>Flagged values are excluded from the metrics they affect and retained for source correction.</li>
      </ul>
    </section>
  </>;
}
