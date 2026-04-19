import { Link } from 'react-router-dom';
import { PARequest } from '../types';
import { getDocumentUrl } from '../api/client';

interface PAVisualizerProps {
  paRequest: PARequest;
  backPath: string;
}

const statusColor = (status: string): string => {
  if (status.includes('completed') || status === 'approved') return 'bg-pi-green text-white';
  if (status.includes('failed') || status === 'denied') return 'bg-pi-red text-white';
  if (status.includes('appealing')) return 'border border-pi-border-hover text-pi-muted';
  return 'bg-pi-blue text-white';
};

export default function PAVisualizer({ paRequest, backPath }: PAVisualizerProps) {
  const pa = paRequest;

  return (
    <div>
      <div className="flex items-center justify-between mb-10">
        <Link
          to={backPath}
          className="pi-btn-secondary text-sm"
        >
          Back
        </Link>
        <div className="flex items-center gap-4">
          <span className="text-pi-muted font-mono text-sm">{pa.pa_request_id}</span>
          <span className={`pi-badge ${statusColor(pa.status)}`}>
            {pa.status.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {pa.error && (
        <div className="border border-pi-red bg-[rgba(197,38,38,0.08)] p-5 mb-10">
          <h3 className="text-pi-red font-mono font-semibold mb-1">Error</h3>
          <p className="text-pi-red text-sm font-mono">{pa.error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
        <div className="pi-card p-6">
          <h3 className="pi-label mb-4">Patient Information</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-pi-muted">Name</dt>
              <dd className="text-pi-body">{pa.patient.first_name} {pa.patient.last_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">DOB</dt>
              <dd className="text-pi-body">{pa.patient.dob}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Insurance</dt>
              <dd className="text-pi-body">{pa.patient.insurance_provider}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Insurance ID</dt>
              <dd className="text-pi-body font-mono text-xs">{pa.patient.insurance_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Phone</dt>
              <dd className="text-pi-body font-mono">{pa.patient.phone}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Address</dt>
              <dd className="text-pi-body text-right max-w-[200px]">{pa.patient.address}</dd>
            </div>
          </dl>
        </div>

        <div className="pi-card p-6">
          <h3 className="pi-label mb-4">Physician Information</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-pi-muted">Name</dt>
              <dd className="text-pi-body">{pa.physician.first_name} {pa.physician.last_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">NPI</dt>
              <dd className="text-pi-body font-mono">{pa.physician.npi}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Specialty</dt>
              <dd className="text-pi-body">{pa.physician.specialty}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Phone</dt>
              <dd className="text-pi-body font-mono">{pa.physician.phone}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Fax</dt>
              <dd className="text-pi-body font-mono">{pa.physician.fax}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="border-t border-pi-border pt-10 mb-10">
        <div className="pi-card p-6">
          <h3 className="pi-label mb-4">Request Details</h3>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-pi-muted">Created</dt>
              <dd className="text-pi-body font-mono text-xs">{new Date(pa.created_at).toLocaleString()}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Updated</dt>
              <dd className="text-pi-body font-mono text-xs">{new Date(pa.updated_at).toLocaleString()}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Attempt</dt>
              <dd className="text-pi-body">{pa.attempt_number}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-pi-muted">Attempt Hash</dt>
              <dd className="text-pi-subtle font-mono text-xs">{pa.attempt_hash}</dd>
            </div>
            {pa.outcome && (
              <div className="flex justify-between">
                <dt className="text-pi-muted">Outcome</dt>
                <dd className="text-pi-body">{pa.outcome}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {pa.transcript && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Transcript</h3>
            <p className="text-pi-body text-sm font-mono whitespace-pre-wrap leading-relaxed">{pa.transcript}</p>
          </div>
        </div>
      )}

      {pa.entities && pa.entities.length > 0 && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Extracted Entities</h3>
            <div className="flex flex-wrap gap-2">
              {pa.entities.map((entity: any, i: number) => (
                <span key={i} className="border border-pi-border-card px-3 py-1 font-mono text-sm text-pi-body">
                  {typeof entity === 'string' ? entity : JSON.stringify(entity)}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {pa.treatments_requiring_pa && pa.treatments_requiring_pa.length > 0 && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Treatments Requiring PA</h3>
            <div>
              {pa.treatments_requiring_pa.map((treatment: any, i: number) => (
                <div key={i} className="border-b border-pi-border py-3 font-mono text-sm text-pi-body">
                  {typeof treatment === 'string' ? treatment : JSON.stringify(treatment, null, 2)}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {pa.selected_forms && pa.selected_forms.length > 0 && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Selected Forms</h3>
            <div>
              {pa.selected_forms.map((form: any, i: number) => (
                <div key={i} className="border-b border-pi-border py-3 font-mono text-sm text-pi-body">
                  {typeof form === 'string' ? form : JSON.stringify(form, null, 2)}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {pa.memories && pa.memories.length > 0 && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Memories</h3>
            <div>
              {pa.memories.map((memory: any, i: number) => (
                <div key={i} className="border-b border-pi-border py-3 font-mono text-sm text-pi-body">
                  {typeof memory === 'string' ? memory : JSON.stringify(memory, null, 2)}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {pa.completed_form_s3_keys && pa.completed_form_s3_keys.length > 0 && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Completed Documents</h3>
            <div className="space-y-3">
              {pa.completed_form_s3_keys.map((_key: string, i: number) => (
                <Link
                  key={i}
                  to={`/pa/${pa.pa_request_id}/pdf/${pa.attempt_hash}/${i}`}
                  className="flex items-center gap-4 border border-pi-border-card p-4 hover:border-pi-border-hover hover:-translate-y-1 transition-all duration-150 ease-pi"
                >
                  <span className="font-mono text-pi-subtle text-sm">[PDF]</span>
                  <span className="text-pi-body font-mono text-sm hover:text-white">Document {i + 1}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}

      {pa.submission_result && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Submission Result</h3>
            <pre className="text-pi-body font-mono text-sm bg-pi-surface border border-pi-border p-6 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(pa.submission_result, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {pa.rejection_history && pa.rejection_history.length > 0 && (
        <div className="border-t border-pi-border pt-10 mb-10">
          <div className="pi-card p-6">
            <h3 className="pi-label mb-4">Rejection History</h3>
            <div className="space-y-3">
              {pa.rejection_history.map((rejection: any, i: number) => (
                <div key={i} className="border border-pi-red bg-[rgba(197,38,38,0.05)] p-4">
                  <pre className="text-pi-red font-mono text-sm overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(rejection, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
