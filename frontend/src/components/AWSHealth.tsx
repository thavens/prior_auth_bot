import { useState, useEffect } from 'react';
import { getAWSHealth } from '../api/client';
import { AWSHealthResponse, AWSComponent } from '../types';

interface AWSHealthProps {
  onHealthData?: (data: AWSHealthResponse) => void;
}

export default function AWSHealth({ onHealthData }: AWSHealthProps) {
  const [health, setHealth] = useState<AWSHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    try {
      const data = await getAWSHealth();
      setHealth(data);
      setError(null);
      onHealthData?.(data);
    } catch {
      setError('Failed to fetch AWS health');
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="pi-card p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="pi-heading text-xl">AWS Health</h2>
        {health && (
          <span
            className={`pi-badge ${
              health.overall === 'healthy'
                ? 'bg-pi-green text-white'
                : 'bg-pi-red text-white'
            }`}
          >
            {health.overall}
          </span>
        )}
      </div>

      {error && (
        <p className="text-pi-red text-sm mb-3">{error}</p>
      )}

      {!health && !error && (
        <p className="text-pi-muted font-mono text-sm">Loading...</p>
      )}

      {health && (
        <div className="max-h-80 overflow-y-auto">
          {health.components.map((comp: AWSComponent) => (
            <div
              key={comp.name}
              className="flex items-center justify-between border-b border-pi-border py-3"
            >
              <div className="flex items-center gap-3">
                <span
                  className={`w-2 h-2 flex-shrink-0 ${
                    comp.status === 'healthy' ? 'bg-pi-green' : 'bg-pi-red'
                  }`}
                />
                <div>
                  <span className="text-pi-body text-sm">{comp.name}</span>
                  {comp.error && (
                    <p className="text-pi-red text-xs mt-0.5">{comp.error}</p>
                  )}
                </div>
              </div>
              <span className="pi-badge border border-pi-border-card text-pi-muted">
                {comp.type}
              </span>
            </div>
          ))}
          {health.checked_at && (
            <p className="text-pi-subtle font-mono text-xs text-right pt-3">
              Last checked: {new Date(health.checked_at).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
