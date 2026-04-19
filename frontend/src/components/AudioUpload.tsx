import { useState, useRef, DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { createPARequest } from '../api/client';
import { PatientRecord, PhysicianRecord } from '../types';
import PhysicianSelector from './PhysicianSelector';
import PatientSelector from './PatientSelector';

const ACCEPTED_TYPES = '.wav,.mp3,.m4a,.ogg,.flac,.webm';

export default function AudioUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ pa_request_id: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedPhysician, setSelectedPhysician] = useState<PhysicianRecord | null>(null);
  const [selectedPatient, setSelectedPatient] = useState<PatientRecord | null>(null);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleSubmit = async () => {
    if (!file || !selectedPatient || !selectedPhysician) return;
    setUploading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('audio_file', file);
    formData.append('patient_id', selectedPatient.patient_id);
    formData.append('physician_id', selectedPhysician.physician_id);

    try {
      const data = await createPARequest(formData);
      setResult(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const canSubmit = file && selectedPatient && selectedPhysician && !uploading;

  return (
    <div className="pi-card p-8">
      <h2 className="pi-heading text-2xl mb-6">Submit Prior Authorization</h2>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border border-dashed p-10 text-center cursor-pointer transition-all duration-150 ease-pi mb-8 ${
          dragging
            ? 'border-pi-blue bg-[rgba(62,119,241,0.05)]'
            : file
            ? 'border-pi-green bg-[rgba(85,204,88,0.05)]'
            : 'border-pi-border-card hover:border-pi-border-hover'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          onChange={handleFileChange}
          className="hidden"
        />
        {file ? (
          <div>
            <p className="text-pi-green font-mono font-medium">{file.name}</p>
            <p className="text-pi-muted font-mono text-sm mt-1">
              {(file.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
        ) : (
          <div>
            <p className="text-pi-body">Drop an audio file here or click to browse</p>
            <p className="text-pi-subtle font-mono text-sm mt-1">WAV, MP3, M4A, OGG, FLAC, WebM</p>
          </div>
        )}
      </div>

      <div className="space-y-4 mb-8">
        <PhysicianSelector onSelect={setSelectedPhysician} />
        <PatientSelector
          physicianId={selectedPhysician?.physician_id || ''}
          onSelect={setSelectedPatient}
        />
      </div>

      {selectedPatient && (
        <div className="border border-pi-border-card bg-[rgba(62,119,241,0.05)] p-3 mb-6 font-mono text-sm text-pi-body">
          <span className="text-pi-muted">Selected: </span>
          {selectedPatient.first_name} {selectedPatient.last_name} — DOB: {selectedPatient.dob} — {selectedPatient.insurance_provider} ({selectedPatient.insurance_id})
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="pi-btn-primary w-full py-3 text-base"
      >
        {uploading ? 'Submitting...' : 'Submit Prior Authorization'}
      </button>

      {error && (
        <div className="mt-6 border border-pi-red bg-[rgba(197,38,38,0.08)] p-4">
          <p className="text-pi-red text-sm font-mono">{error}</p>
        </div>
      )}

      {result && (
        <div className="mt-6 border border-pi-green bg-[rgba(85,204,88,0.08)] p-4">
          <p className="text-pi-green font-mono font-medium">PA Request Created Successfully</p>
          <p className="text-pi-body font-mono text-sm mt-1">
            ID: {result.pa_request_id}
          </p>
          <Link
            to={`/pa/${result.pa_request_id}?from=physician`}
            className="group inline-flex items-center gap-2 mt-3 text-pi-body font-mono text-sm hover:text-white transition-colors"
          >
            Track this request
            <span className="transition-transform duration-150 group-hover:translate-x-1">&rarr;</span>
          </Link>
        </div>
      )}
    </div>
  );
}
