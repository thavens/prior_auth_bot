import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { searchPARequests } from '../api/client';
import { PARequestSummary } from '../types';

interface PASearchProps {
  fromPage: string;
}

const statusColor = (status: string): string => {
  if (status.includes('completed') || status === 'approved') return 'bg-pi-green text-white';
  if (status.includes('failed') || status === 'denied') return 'bg-pi-red text-white';
  if (status.includes('appealing')) return 'border border-pi-border-hover text-pi-muted';
  return 'bg-pi-blue text-white';
};

export default function PASearch({ fromPage }: PASearchProps) {
  const [patient, setPatient] = useState('');
  const [physician, setPhysician] = useState('');
  const [results, setResults] = useState<PARequestSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const navigate = useNavigate();

  const handleSearch = async () => {
    setLoading(true);
    setSearched(true);
    try {
      const data = await searchPARequests(
        patient || undefined,
        physician || undefined
      );
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div className="pi-card p-8">
      <h2 className="pi-heading text-xl mb-6">Search PA Requests</h2>
      <div className="flex flex-wrap gap-4 mb-6">
        <input
          type="text"
          placeholder="Patient name..."
          value={patient}
          onChange={(e) => setPatient(e.target.value)}
          onKeyDown={handleKeyDown}
          className="pi-input flex-1 min-w-[200px] text-sm"
        />
        <input
          type="text"
          placeholder="Physician name..."
          value={physician}
          onChange={(e) => setPhysician(e.target.value)}
          onKeyDown={handleKeyDown}
          className="pi-input flex-1 min-w-[200px] text-sm"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="pi-btn-primary px-8"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {searched && results.length === 0 && !loading && (
        <p className="text-pi-muted text-center py-6 font-mono text-sm">No results found.</p>
      )}

      <div>
        {results.map((r) => (
          <div
            key={r.pa_request_id}
            onClick={() => navigate(`/pa/${r.pa_request_id}?from=${fromPage}`)}
            className="border-b border-pi-border py-4 cursor-pointer hover:bg-pi-surface-hover transition-all duration-150 ease-pi px-2"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-sm text-pi-body">{r.pa_request_id}</span>
              <span className={`pi-badge ${statusColor(r.status)}`}>
                {r.status.replace(/_/g, ' ')}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-pi-muted font-mono">
              <span>Patient: {r.patient_name}</span>
              <span>Physician: {r.physician_name}</span>
              <span>Attempt: {r.attempt_number}</span>
              <span>Created: {new Date(r.created_at).toLocaleString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
