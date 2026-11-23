import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/inter/latin-700.css';
import Dashboard from './Dashboard';
import Shipments from './Shipments';
import Quality from './Quality';
import Upload from './Upload';
import Ask from './Ask';
import './style.css';

const pages = { dashboard: 'Dashboard', shipments: 'Shipments', quality: 'Data Quality', ask: 'Ask the Data' };

function route() {
  const page = window.location.hash.slice(1);
  return Object.hasOwn(pages, page) ? page : 'dashboard';
}

function App() {
  const [page, setPage] = useState(route);
  const [revision, setRevision] = useState(0);
  const [grace, setGrace] = useState(0);
  const [upload, setUpload] = useState(false);
  const [selected, setSelected] = useState('');
  useEffect(() => {
    const onHash = () => {
      setPage(route());
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  function openShipment(id) {
    setSelected(id);
    window.location.hash = 'shipments';
  }

  return <>
    <header className="app-header">
      <div className="header-inner">
        <a href="#dashboard" className="brand"><span className="brand-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m3 8 9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5m-9 5v8M7.5 5.5l9 5"/></svg>
        </span>Freight Visibility</a>
        <nav aria-label="Main navigation">{Object.entries(pages).map(([key, title]) =>
          <a href={`#${key}`} key={key} aria-current={page === key ? 'page' : undefined}>{title}</a>)}</nav>
        <button className="upload-button" onClick={() => setUpload(true)}>Upload CSV</button>
      </div>
    </header>
    <main aria-label={pages[page]}>
      {page === 'dashboard' && <Dashboard grace={grace} setGrace={setGrace} revision={revision} navigate={openShipment} />}
      {page === 'shipments' && <Shipments grace={grace} revision={revision} selected={selected} setSelected={setSelected} />}
      {page === 'ask' && <Ask key={revision} />}
      {page === 'quality' && <Quality revision={revision} navigate={openShipment} />}
    </main>
    {upload && <Upload onClose={() => setUpload(false)} onComplete={() => setRevision(value => value + 1)} />}
  </>;
}

createRoot(document.getElementById('root')).render(<App />);
