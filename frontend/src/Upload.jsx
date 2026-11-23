import React, { useEffect, useRef, useState } from 'react';
import { Reconciliation } from './components';

function sendFile(file, mode, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/upload?mode=${mode}`);
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100));
    };
    xhr.onload = () => {
      let body;
      try { body = JSON.parse(xhr.responseText); } catch { /* use generic message below */ }
      if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body);
      else reject(new Error(typeof body?.detail === 'string' ? body.detail : 'Upload failed. Please try again.'));
    };
    xhr.onerror = () => reject(new Error('Could not reach the upload service.'));
    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

export default function Upload({ onClose, onComplete }) {
  const dialog = useRef(null);
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState('replace');
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);
  useEffect(() => { dialog.current.showModal(); }, []);

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (file.size > 10 * 1024 * 1024) {
      setError('The file exceeds the 10 MB limit.');
      return;
    }
    setProgress(0);
    try {
      const result = await sendFile(file, mode, setProgress);
      setReport(result);
      onComplete();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setProgress(null);
    }
  }

  return <dialog ref={dialog} aria-labelledby="upload-title" onCancel={event => {
    event.preventDefault();
    if (progress == null) onClose();
  }}>
    <div className="section-heading">
      <h2 id="upload-title">{report ? 'Cleaning summary' : 'Upload shipment CSV'}</h2>
      <button className="secondary" onClick={onClose} disabled={progress != null}>{report ? 'Done' : 'Close'}</button>
    </div>
    {report ? <>
      <p>{report.filename} · {report.uploaded_rows} newly uploaded rows</p>
      <Reconciliation report={report} />
      <p>{report.exact_duplicates} exact duplicates · {report.conflicting_duplicates} conflicting rows</p>
      <p>{report.errors} shipments with errors · {report.warnings} with warnings</p>
      <p>{report.delivered_excluded} deliveries excluded for dates · {report.weight_excluded} weights excluded</p>
      <a href="#quality" onClick={onClose}>Review data quality</a>
    </> : <form className="upload-form" onSubmit={submit}>
      <label>CSV file <input type="file" accept=".csv,text/csv" required disabled={progress != null}
        onChange={event => setFile(event.target.files[0] || null)} /></label>
      <label>Upload mode <select value={mode} disabled={progress != null} onChange={event => setMode(event.target.value)}>
        <option value="replace">Replace active shipments</option>
        <option value="append">Append and deduplicate</option>
      </select></label>
      <p className="muted">{mode === 'replace' ? 'The file becomes the active shipment snapshot. Earlier batches stay in the audit store.' : 'Incoming rows compete with active source rows using the deduplication rules.'}</p>
      {error && <p className="state error" role="alert">{error}</p>}
      {progress != null && <div role="status"><progress value={progress === 100 ? undefined : progress} max="100" />
        <p>{progress === 100 ? 'Cleaning and saving shipments…' : `Uploading… ${progress}%`}</p></div>}
      <button disabled={!file || progress != null}>Upload CSV</button>
    </form>}
  </dialog>;
}
