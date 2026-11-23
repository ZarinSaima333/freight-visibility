import { useEffect, useState } from 'react';

export async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'The request failed. Please try again.');
  }
  return response.json();
}

export function useRequest(path, revision = 0) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    request(path, { signal: controller.signal })
      .then(data => setState({ data }))
      .catch(error => {
        if (error.name !== 'AbortError') setState({ error: error.message });
      });
    return () => controller.abort();
  }, [path, revision]);
  return state;
}

export const cities = {
  BDCGP: 'Chattogram', BDDAC: 'Dhaka (air)', VNSGN: 'Ho Chi Minh City',
  INNSA: 'Nhava Sheva', INMAA: 'Chennai', CNSHA: 'Shanghai', LKCMB: 'Colombo',
  NLRTM: 'Rotterdam', ESVLC: 'Valencia', DEHAM: 'Hamburg', USNYC: 'New York',
  GBFXT: 'Felixstowe', ESALG: 'Algeciras', PLGDN: 'Gdansk', FRLEH: 'Le Havre',
};
export const laneName = lane => lane?.split(' -> ').map(code => cities[code] || code || 'Unknown port').join(' → ');
export const number = (value, digits = 0) => new Intl.NumberFormat('en', {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
}).format(value);
export const percent = value => value == null ? '—' : number(value, 1) + '%';
export const display = value => value == null || value === '' ? '—' : typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value);
