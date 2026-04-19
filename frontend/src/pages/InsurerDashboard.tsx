import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { getInsurerQueue, connectWebSocket } from '../api/client';
import { InsurerQueueItem } from '../types';

export default function InsurerDashboard() {
  const [queue, setQueue] = useState<InsurerQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<number | null>(null);

  const fetchQueue = useCallback(async () => {
    try {
      const data = await getInsurerQueue();
      setQueue(data ?? []);
      setError(null);
    } catch {
      setError('Failed to load insurer queue');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();

    intervalRef.current = window.setInterval(fetchQueue, 10000);

    wsRef.current = connectWebSocket((data) => {
      if (data.type === 'status_update') {
        fetchQueue();
      }
    });

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      wsRef.current?.close();
    };
  }, [fetchQueue]);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div>
      <nav className="pi-nav px-6">
        <div className="max-w-pi mx-auto w-full flex items-center justify-between">
          <h1 className="font-mono text-lg font-semibold tracking-tight text-pi-text">Insurer Portal</h1>
          <div className="flex items-center gap-3">
            <Link to="/" className="pi-btn-secondary text-sm">
              Physician Dashboard
            </Link>
            <Link to="/pipeline" className="pi-btn-secondary text-sm">
              Pipeline Dashboard
            </Link>
          </div>
        </div>
      </nav>

      <main className="max-w-pi mx-auto px-6 py-16">
        <h2 className="pi-heading text-3xl mb-10">Pending Reviews</h2>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="text-pi-muted font-mono text-base">Loading queue...</div>
          </div>
        )}

        {error && !loading && (
          <div className="border border-pi-red bg-[rgba(197,38,38,0.08)] p-8 text-center">
            <p className="text-pi-red font-mono text-lg">{error}</p>
          </div>
        )}

        {!loading && !error && queue.length === 0 && (
          <div className="pi-card p-12 text-center">
            <p className="text-pi-muted font-mono text-lg">No pending requests to review.</p>
            <p className="text-pi-subtle font-mono text-sm mt-2">
              New requests will appear here automatically.
            </p>
          </div>
        )}

        {!loading && !error && queue.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {queue.map((item) => (
              <Link
                key={item.pa_request_id}
                to={`/insurer/review/${item.pa_request_id}`}
                className="pi-card pi-card-hover p-6 block"
              >
                <div className="flex items-center justify-between mb-4">
                  <span className={`pi-badge ${
                    item.status === 'pending_insurer_review'
                      ? 'bg-pi-blue text-white'
                      : 'border border-pi-border-hover text-pi-muted'
                  }`}>
                    {item.status.replace(/_/g, ' ')}
                  </span>
                  {item.attempt_number > 1 && (
                    <span className="pi-badge bg-[rgba(197,38,38,0.15)] text-pi-red">
                      Attempt {item.attempt_number}
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <span className="text-pi-muted font-mono text-xs uppercase tracking-wide">Patient</span>
                    <p className="text-pi-body font-mono text-sm mt-0.5">{item.patient_name}</p>
                  </div>

                  <div>
                    <span className="text-pi-muted font-mono text-xs uppercase tracking-wide">Physician</span>
                    <p className="text-pi-body font-mono text-sm mt-0.5">{item.physician_name}</p>
                  </div>

                  <div>
                    <span className="text-pi-muted font-mono text-xs uppercase tracking-wide">Insurance</span>
                    <p className="text-pi-body font-mono text-sm mt-0.5">{item.insurance_provider}</p>
                  </div>

                  <div>
                    <span className="text-pi-muted font-mono text-xs uppercase tracking-wide">Treatment</span>
                    <p className="text-pi-body text-sm mt-0.5 line-clamp-2">{item.treatment_text}</p>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-pi-border flex items-center justify-between">
                  <span className="text-pi-subtle font-mono text-xs">{formatDate(item.created_at)}</span>
                  <span className="text-pi-blue font-mono text-xs">Review &rarr;</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
