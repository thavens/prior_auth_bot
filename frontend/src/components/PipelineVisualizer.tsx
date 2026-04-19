import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { searchPARequests, connectWebSocket } from '../api/client';
import { PARequestSummary, AWSHealthResponse } from '../types';

interface Stage {
  label: string;
  number: string;
  status: string;
}

const stages: Stage[] = [
  { label: 'Entity Extraction', number: '01', status: 'step_1_entity_extraction' },
  { label: 'PA Determination', number: '02', status: 'step_2_pa_determination' },
  { label: 'Form Selection', number: '03', status: 'step_3_form_selection' },
  { label: 'Memory Retrieval', number: '04', status: 'step_4_memory_retrieval' },
  { label: 'Doc Population', number: '05', status: 'step_5_document_population' },
  { label: 'Doc Submission', number: '06', status: 'step_6_document_submission' },
  { label: 'Insurer Review', number: '07', status: 'pending_insurer_review' },
  { label: 'Outcome Handling', number: '08', status: 'step_7_outcome_handling' },
];

interface PipelineVisualizerProps {
  healthData: AWSHealthResponse | null;
}

export default function PipelineVisualizer({ healthData }: PipelineVisualizerProps) {
  const [stageCounts, setStageCounts] = useState<Record<string, number>>({});
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [stageRequests, setStageRequests] = useState<PARequestSummary[]>([]);
  const [loadingStage, setLoadingStage] = useState(false);
  const navigate = useNavigate();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const loadCounts = async () => {
      try {
        const all = await searchPARequests();
        const counts: Record<string, number> = {};
        for (const r of all) {
          counts[r.status] = (counts[r.status] || 0) + 1;
        }
        setStageCounts(counts);
      } catch {
        // ignore
      }
    };

    loadCounts();

    wsRef.current = connectWebSocket((data) => {
      if (data.type === 'status_update') {
        setStageCounts((prev) => {
          const next = { ...prev };
          next[data.status] = (next[data.status] || 0) + 1;
          return next;
        });
      }
    });

    return () => {
      wsRef.current?.close();
    };
  }, []);

  const handleStageClick = async (status: string) => {
    if (selectedStage === status) {
      setSelectedStage(null);
      return;
    }
    setSelectedStage(status);
    setLoadingStage(true);
    try {
      const all = await searchPARequests();
      setStageRequests(all.filter((r: PARequestSummary) => r.status === status));
    } catch {
      setStageRequests([]);
    } finally {
      setLoadingStage(false);
    }
  };

  const isStageHealthy = (_stageStatus: string): boolean => {
    if (!healthData) return true;
    return healthData.overall === 'healthy';
  };

  return (
    <div className="pi-card p-8">
      <h2 className="pi-heading text-xl mb-8">Pipeline Stages</h2>

      <div className="flex items-center gap-0 overflow-x-auto pb-2">
        {stages.map((stage, i) => (
          <div key={stage.status} className="flex items-center">
            <button
              onClick={() => handleStageClick(stage.status)}
              className={`flex flex-col items-center p-5 min-w-[140px] border transition-all duration-150 ease-pi ${
                selectedStage === stage.status
                  ? 'border-pi-border-hover bg-pi-surface-hover'
                  : 'border-pi-border-card hover:border-pi-border-hover hover:bg-pi-surface-hover'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="pi-step-number">{stage.number}</span>
                <span
                  className={`w-2 h-2 ${
                    isStageHealthy(stage.status) ? 'bg-pi-green' : 'bg-pi-red'
                  }`}
                />
              </div>
              <span className="text-pi-body text-xs font-mono text-center leading-tight">
                {stage.label}
              </span>
              <span className="text-pi-body text-2xl font-mono font-light mt-2">
                {stageCounts[stage.status] || 0}
              </span>
            </button>
            {i < stages.length - 1 && (
              <div className="w-6 h-px bg-pi-border-card flex-shrink-0" />
            )}
          </div>
        ))}
      </div>

      {selectedStage && (
        <div className="mt-8 border-t border-pi-border pt-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="pi-label">
              {stages.find((s) => s.status === selectedStage)?.label} — Active Requests
            </h3>
            <button
              onClick={() => setSelectedStage(null)}
              className="text-pi-muted hover:text-white font-mono text-sm transition-colors"
            >
              Close
            </button>
          </div>

          {loadingStage ? (
            <p className="text-pi-muted text-center py-6 font-mono text-sm">Loading...</p>
          ) : stageRequests.length === 0 ? (
            <p className="text-pi-muted text-center py-6 font-mono text-sm">No requests at this stage.</p>
          ) : (
            <div className="max-h-60 overflow-y-auto">
              {stageRequests.map((r) => (
                <div
                  key={r.pa_request_id}
                  onClick={() => navigate(`/pa/${r.pa_request_id}?from=pipeline`)}
                  className="border-b border-pi-border py-3 cursor-pointer hover:bg-pi-surface-hover transition-all duration-150 ease-pi px-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-pi-body text-sm font-mono">{r.pa_request_id}</span>
                    <span className="text-pi-subtle font-mono text-xs">Attempt {r.attempt_number}</span>
                  </div>
                  <div className="flex gap-4 mt-1 text-xs text-pi-muted font-mono">
                    <span>Patient: {r.patient_name}</span>
                    <span>Physician: {r.physician_name}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
