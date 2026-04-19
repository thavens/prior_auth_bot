import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getInsurerPARequest, submitInsurerDecision, getDocumentUrl } from '../api/client';
import { PARequest, InsurerDecision } from '../types';

export default function InsurerReviewPage() {
  const { paRequestId } = useParams<{ paRequestId: string }>();
  const navigate = useNavigate();
  const [paRequest, setPaRequest] = useState<PARequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Decision state
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [rejectionReasons, setRejectionReasons] = useState<string[]>([]);
  const [newReason, setNewReason] = useState('');
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!paRequestId) return;
    setLoading(true);
    getInsurerPARequest(paRequestId)
      .then(setPaRequest)
      .catch(() => setError('Failed to load PA request'))
      .finally(() => setLoading(false));
  }, [paRequestId]);

  const handleApprove = async () => {
    if (!paRequestId) return;
    setSubmitting(true);
    try {
      const decision: InsurerDecision = {
        pa_request_id: paRequestId,
        decision: 'approved',
        rejection_reasons: [],
        feedback: '',
      };
      await submitInsurerDecision(paRequestId, decision);
      setSuccessMessage('PA request approved successfully.');
      setShowApproveConfirm(false);
      setTimeout(() => navigate('/insurer'), 2000);
    } catch {
      setError('Failed to submit approval');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!paRequestId) return;
    if (rejectionReasons.length === 0) return;
    setSubmitting(true);
    try {
      const decision: InsurerDecision = {
        pa_request_id: paRequestId,
        decision: 'rejected',
        rejection_reasons: rejectionReasons,
        feedback,
      };
      await submitInsurerDecision(paRequestId, decision);
      setSuccessMessage('PA request rejected. The physician will be notified.');
      setTimeout(() => navigate('/insurer'), 2000);
    } catch {
      setError('Failed to submit rejection');
    } finally {
      setSubmitting(false);
    }
  };

  const addReason = () => {
    const trimmed = newReason.trim();
    if (trimmed && !rejectionReasons.includes(trimmed)) {
      setRejectionReasons([...rejectionReasons, trimmed]);
      setNewReason('');
    }
  };

  const removeReason = (index: number) => {
    setRejectionReasons(rejectionReasons.filter((_, i) => i !== index));
  };

  if (loading) {
    return (
      <div className="px-6 py-16">
        <div className="max-w-pi mx-auto flex items-center justify-center py-20">
          <div className="text-pi-muted font-mono text-base">Loading PA request...</div>
        </div>
      </div>
    );
  }

  if (error && !paRequest) {
    return (
      <div className="px-6 py-16">
        <div className="max-w-pi mx-auto">
          <Link to="/insurer" className="pi-btn-secondary text-sm mb-8 inline-block">
            Back to Queue
          </Link>
          <div className="border border-pi-red bg-[rgba(197,38,38,0.08)] p-8 text-center">
            <p className="text-pi-red font-mono text-lg">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!paRequest) return null;

  const pa = paRequest;

  return (
    <div className="px-6 py-16">
      <div className="max-w-pi mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-10">
          <Link to="/insurer" className="pi-btn-secondary text-sm">
            Back to Queue
          </Link>
          <div className="flex items-center gap-4">
            <span className="text-pi-muted font-mono text-sm">{pa.pa_request_id}</span>
            <span className="pi-badge bg-pi-blue text-white">
              {pa.status.replace(/_/g, ' ')}
            </span>
            {pa.attempt_number > 1 && (
              <span className="pi-badge bg-[rgba(197,38,38,0.15)] text-pi-red">
                Attempt {pa.attempt_number}
              </span>
            )}
          </div>
        </div>

        {/* Success message */}
        {successMessage && (
          <div className="border border-pi-green bg-[rgba(85,204,88,0.08)] p-5 mb-10">
            <p className="text-pi-green font-mono text-lg text-center">{successMessage}</p>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="border border-pi-red bg-[rgba(197,38,38,0.08)] p-5 mb-10">
            <p className="text-pi-red font-mono text-sm">{error}</p>
          </div>
        )}

        {/* Patient & Physician info */}
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
                <dt className="text-pi-muted">Address</dt>
                <dd className="text-pi-body text-right max-w-[200px]">{pa.patient.address}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-pi-muted">Phone</dt>
                <dd className="text-pi-body font-mono">{pa.patient.phone}</dd>
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

        {/* Treatments */}
        {pa.treatments_requiring_pa && pa.treatments_requiring_pa.length > 0 && (
          <div className="border-t border-pi-border pt-10 mb-10">
            <div className="pi-card p-6">
              <h3 className="pi-label mb-4">Treatments Requiring PA</h3>
              <div className="space-y-3">
                {pa.treatments_requiring_pa.map((treatment: any, i: number) => (
                  <div key={i} className="border border-pi-border-card p-4">
                    <div className="space-y-2 text-sm">
                      {treatment.text && (
                        <div>
                          <span className="text-pi-muted font-mono text-xs uppercase">Treatment</span>
                          <p className="text-pi-body mt-0.5">{treatment.text}</p>
                        </div>
                      )}
                      {treatment.category && (
                        <div>
                          <span className="text-pi-muted font-mono text-xs uppercase">Category</span>
                          <p className="text-pi-body mt-0.5">{treatment.category}</p>
                        </div>
                      )}
                      {treatment.pa_reason && (
                        <div>
                          <span className="text-pi-muted font-mono text-xs uppercase">PA Reason</span>
                          <p className="text-pi-body mt-0.5">{treatment.pa_reason}</p>
                        </div>
                      )}
                      {!treatment.text && !treatment.category && (
                        <p className="text-pi-body font-mono text-sm">
                          {typeof treatment === 'string' ? treatment : JSON.stringify(treatment, null, 2)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Selected Forms */}
        {pa.selected_forms && pa.selected_forms.length > 0 && (
          <div className="border-t border-pi-border pt-10 mb-10">
            <div className="pi-card p-6">
              <h3 className="pi-label mb-4">Selected Forms</h3>
              <div>
                {pa.selected_forms.map((form: any, i: number) => (
                  <div key={i} className="border-b border-pi-border py-3 font-mono text-sm text-pi-body">
                    {form.name || form.form_name || (typeof form === 'string' ? form : JSON.stringify(form))}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Completed Documents */}
        {pa.completed_form_s3_keys && pa.completed_form_s3_keys.length > 0 && (
          <div className="border-t border-pi-border pt-10 mb-10">
            <div className="pi-card p-6">
              <h3 className="pi-label mb-4">Completed Documents</h3>
              <div className="space-y-3">
                {pa.completed_form_s3_keys.map((key: string, i: number) => {
                  const stripped = key.replace('pa-completed-forms/', '').replace('.pdf', '');
                  const parts = stripped.split('/');
                  const hash = parts[0] || pa.attempt_hash;
                  const num = parseInt(parts[1], 10) || (i + 1);
                  return (
                    <a
                      key={i}
                      href={getDocumentUrl(pa.pa_request_id, hash, num)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-4 border border-pi-border-card p-4 hover:border-pi-border-hover hover:-translate-y-1 transition-all duration-150 ease-pi"
                    >
                      <span className="font-mono text-pi-subtle text-sm">[PDF]</span>
                      <span className="text-pi-body font-mono text-sm hover:text-white">
                        Document {i + 1}{pa.attempt_number > 1 ? ` (Appeal Attempt ${pa.attempt_number})` : ''}
                      </span>
                    </a>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Rejection History */}
        {pa.rejection_history && pa.rejection_history.length > 0 && (
          <div className="border-t border-pi-border pt-10 mb-10">
            <div className="pi-card p-6">
              <h3 className="pi-label mb-4">Rejection History</h3>
              <div className="space-y-3">
                {pa.rejection_history.map((rejection: any, i: number) => (
                  <div key={i} className="border border-pi-red bg-[rgba(197,38,38,0.05)] p-4">
                    {rejection.rejection_reasons && (
                      <div className="mb-2">
                        <span className="text-pi-red font-mono text-xs uppercase font-semibold">Reasons</span>
                        <ul className="mt-1 space-y-1">
                          {rejection.rejection_reasons.map((reason: string, j: number) => (
                            <li key={j} className="text-pi-red font-mono text-sm">- {reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {rejection.feedback && (
                      <div>
                        <span className="text-pi-red font-mono text-xs uppercase font-semibold">Feedback</span>
                        <p className="text-pi-red font-mono text-sm mt-1">{rejection.feedback}</p>
                      </div>
                    )}
                    {!rejection.rejection_reasons && !rejection.feedback && (
                      <pre className="text-pi-red font-mono text-sm overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(rejection, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Memories / Insights */}
        {pa.memories && pa.memories.length > 0 && (
          <div className="border-t border-pi-border pt-10 mb-10">
            <div className="pi-card p-6">
              <h3 className="pi-label mb-4">Memories &amp; Insights</h3>
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

        {/* Decision Section */}
        {!successMessage && (
          <div className="border-t border-pi-border pt-10 mb-10">
            <div className="pi-card p-6">
              <h3 className="pi-label mb-6">Decision</h3>

              <div className="flex items-center gap-4 mb-6">
                <button
                  onClick={() => {
                    setShowApproveConfirm(true);
                    setShowRejectForm(false);
                  }}
                  disabled={submitting}
                  className="px-8 py-3 bg-pi-green text-white font-mono font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Approve
                </button>
                <button
                  onClick={() => {
                    setShowRejectForm(true);
                    setShowApproveConfirm(false);
                  }}
                  disabled={submitting}
                  className="px-8 py-3 bg-pi-red text-white font-mono font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Reject
                </button>
              </div>

              {/* Approve confirmation */}
              {showApproveConfirm && (
                <div className="border border-pi-green bg-[rgba(85,204,88,0.08)] p-6">
                  <p className="text-pi-body font-mono text-sm mb-4">
                    Are you sure you want to approve this PA request?
                  </p>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleApprove}
                      disabled={submitting}
                      className="px-6 py-2 bg-pi-green text-white font-mono font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                    >
                      {submitting ? 'Submitting...' : 'Confirm Approval'}
                    </button>
                    <button
                      onClick={() => setShowApproveConfirm(false)}
                      disabled={submitting}
                      className="pi-btn-secondary text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Reject form */}
              {showRejectForm && (
                <div className="border border-pi-red bg-[rgba(197,38,38,0.05)] p-6 space-y-6">
                  <div>
                    <label className="pi-label block mb-3">Rejection Reasons</label>
                    <div className="flex items-center gap-3 mb-3">
                      <input
                        type="text"
                        value={newReason}
                        onChange={(e) => setNewReason(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            addReason();
                          }
                        }}
                        placeholder="Enter a rejection reason..."
                        className="pi-input flex-1"
                      />
                      <button
                        onClick={addReason}
                        className="pi-btn-secondary text-sm whitespace-nowrap"
                      >
                        Add Reason
                      </button>
                    </div>
                    {rejectionReasons.length > 0 && (
                      <div className="space-y-2">
                        {rejectionReasons.map((reason, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between border border-pi-border-card p-3"
                          >
                            <span className="text-pi-body font-mono text-sm">{reason}</span>
                            <button
                              onClick={() => removeReason(i)}
                              className="text-pi-red font-mono text-sm hover:opacity-70 ml-4 flex-shrink-0"
                            >
                              X
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="pi-label block mb-3">Feedback</label>
                    <textarea
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                      placeholder="Provide additional feedback for the physician..."
                      rows={4}
                      className="pi-input resize-none"
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleReject}
                      disabled={submitting || rejectionReasons.length === 0}
                      className="px-6 py-2 bg-pi-red text-white font-mono font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {submitting ? 'Submitting...' : 'Submit Rejection'}
                    </button>
                    <button
                      onClick={() => setShowRejectForm(false)}
                      disabled={submitting}
                      className="pi-btn-secondary text-sm"
                    >
                      Cancel
                    </button>
                    {rejectionReasons.length === 0 && (
                      <span className="text-pi-muted font-mono text-xs">Add at least one reason to submit</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
