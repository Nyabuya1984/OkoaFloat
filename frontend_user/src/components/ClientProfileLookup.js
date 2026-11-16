import React, { useState } from 'react';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';

const lookupFields = [
  ['agent_name', 'Client / Agent Name'],
  ['agent_number', 'Agent Number'],
  ['store_number', 'Store Number'],
];

export default function ClientProfileLookup({ onConfirm }) {
  const [field, setField] = useState('agent_number');
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState([]);
  const [selected, setSelected] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);

  const search = async (event) => {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    setSelected(null);
    setConfirmed(false);
    setSearched(false);
    try {
      const url = apiUrl(`/api/sales/clients/lookup?field=${encodeURIComponent(field)}&q=${encodeURIComponent(query.trim())}`);
      const send = () => fetch(url, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      let response = await send();
      if (response.status === 401 && await refreshAuthToken()) response = await send();
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error?.message || 'Unable to search the client directory.');
      }
      setMatches(payload.data?.matches || []);
      setSearched(true);
    } catch (lookupError) {
      setError(lookupError.message || 'Unable to search the client directory.');
    } finally {
      setLoading(false);
    }
  };

  const confirm = () => {
    if (!selected) return;
    onConfirm(selected);
    setConfirmed(true);
  };

  return (
    <section className="client-profile-lookup" aria-label="Look up existing client">
      <div>
        <strong>Check for an existing client</strong>
        <p>Search by name, agent number, or store number before entering a new profile.</p>
      </div>
      <form className="client-profile-lookup-form" onSubmit={search}>
        <label>
          <span>Search using</span>
          <select value={field} onChange={(event) => setField(event.target.value)}>
            {lookupFields.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          <span>Client identifier</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} required />
        </label>
        <button type="submit" disabled={!query.trim() || loading}>
          {loading ? 'Searching…' : 'Search clients'}
        </button>
      </form>
      {error && <p className="client-profile-lookup-error" role="alert">{error}</p>}
      {searched && !matches.length && (
        <p className="client-profile-lookup-message" role="status">
          No existing profile found. Continue as a new client.
        </p>
      )}
      {!!matches.length && (
        <div className="client-profile-lookup-results" aria-label="Matching clients">
          {matches.map((match, index) => (
            <button
              className="client-profile-lookup-result"
              type="button"
              key={`${match.agent_number || match.store_number || match.agent_name}-${index}`}
              aria-pressed={selected === match}
              onClick={() => {
                setSelected(match);
                setConfirmed(false);
              }}
            >
              <strong>{match.agent_name || 'Unnamed client'}</strong>
              <span>{[match.agent_number, match.store_number, match.business_location].filter(Boolean).join(' · ')}</span>
              <small>{match.source || 'Client directory'}</small>
            </button>
          ))}
        </div>
      )}
      {selected && (
        <div className="client-profile-lookup-review">
          <p>
            Review: <strong>{selected.agent_name || 'Unnamed client'}</strong>
            {' · '}{selected.category || 'Category not recorded'}
            {' · '}{selected.business_location || 'Location not recorded'}
            {Object.keys(selected.documents || {}).length > 0 && ' · Previously verified documents found'}
          </p>
          {confirmed ? (
            <span role="status">Profile confirmed and copied into the form.</span>
          ) : (
            <button type="button" onClick={confirm}>Confirm profile details</button>
          )}
        </div>
      )}
    </section>
  );
}
