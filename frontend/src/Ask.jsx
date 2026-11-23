import React, { useState } from 'react';
import { request, useRequest } from './api';
import { Badge, Status, Table } from './components';

const examples = [
  'Which carrier is delayed the most?',
  'How many shipments went from Chattogram to Rotterdam?',
  'On-time percentage for air shipments?',
  'Show the 5 heaviest shipments',
];

export default function Ask() {
  const status = useRequest('/api/ask/status');
  const [question, setQuestion] = useState('');
  const [conversation, setConversation] = useState([]);
  const [pending, setPending] = useState('');
  const [error, setError] = useState('');

  async function ask(text) {
    const clean = text.trim();
    if (!clean || pending) return;
    setPending(clean);
    setQuestion('');
    setError('');
    try {
      const result = await request('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: clean, history: conversation.slice(-6).map(turn => turn.question) }),
      });
      setConversation(turns => [...turns, { question: clean, ...result }]);
    } catch (failure) {
      setError(failure.message);
      setQuestion(clean);
    } finally {
      setPending('');
    }
  }

  return <>
    <section className="card">
      <div className="section-heading">
        <h2>Ask the Data</h2>
        <Status state={status}>{data => data.mock_mode ? <Badge value="Mock mode" tone="warning" /> : null}</Status>
      </div>
      <p className="muted">Ask a question about the active shipment snapshot. On-time questions use zero grace days unless specified.</p>
      <div className="examples">{examples.map(example => <button type="button" className="secondary" key={example}
        disabled={!!pending} onClick={() => ask(example)}>{example}</button>)}</div>
      <form className="ask-form" onSubmit={event => { event.preventDefault(); ask(question); }}>
        <label className="field-label" htmlFor="question">Your question</label>
        <div><input id="question" value={question} maxLength={1000} onChange={event => setQuestion(event.target.value)}
          placeholder="Ask about delays, carriers, or trade lanes…" />
        <button disabled={!question.trim() || !!pending}>Ask</button></div>
      </form>
      {error && <p className="state error" role="alert">{error}</p>}
    </section>
    {pending && <p className="state" role="status">Looking up “{pending}”…</p>}
    {[...conversation].reverse().map((turn, index) => <section className="card answer" key={conversation.length - index}>
      <h2>{turn.question}</h2>
      <p>{turn.answer}</p>
      <details><summary>SQL used</summary><pre><code>{turn.sql}</code></pre></details>
      <h3>Query results</h3>
      <Table columns={turn.columns.map((column, i) => [i, column])} rows={turn.rows} empty="The query returned no rows." />
    </section>)}
  </>;
}
