import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { getPARequest } from '../api/client';
import { PARequest } from '../types';
import PAVisualizer from '../components/PAVisualizer';

export default function PAVisualizerPage() {
  const { paRequestId } = useParams<{ paRequestId: string }>();
  const [searchParams] = useSearchParams();
  const [paRequest, setPaRequest] = useState<PARequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const from = searchParams.get('from');
  const backPath = from === 'pipeline' ? '/pipeline' : '/';

  useEffect(() => {
    if (!paRequestId) return;
    setLoading(true);
    getPARequest(paRequestId)
      .then(setPaRequest)
      .catch(() => setError('Failed to load PA request'))
      .finally(() => setLoading(false));
  }, [paRequestId]);

  return (
    <div className="px-6 py-16">
      <div className="max-w-pi mx-auto">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="text-pi-muted font-mono text-base">Loading PA request...</div>
          </div>
        )}
        {error && (
          <div className="border border-pi-red bg-[rgba(197,38,38,0.08)] p-8 text-center">
            <p className="text-pi-red font-mono text-lg">{error}</p>
          </div>
        )}
        {paRequest && <PAVisualizer paRequest={paRequest} backPath={backPath} />}
      </div>
    </div>
  );
}
