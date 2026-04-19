import { useState, useEffect } from 'react';
import { getPatients, createPatient } from '../api/client';
import { PatientRecord } from '../types';

interface Props {
  physicianId: string;
  onSelect: (patient: PatientRecord | null) => void;
}

export default function PatientSelector({ physicianId, onSelect }: Props) {
  const [patients, setPatients] = useState<PatientRecord[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [dob, setDob] = useState('');
  const [insuranceProvider, setInsuranceProvider] = useState('medi-cal');
  const [insuranceId, setInsuranceId] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');

  const fetchPatients = () => {
    if (!physicianId) return;
    setLoading(true);
    getPatients(physicianId)
      .then(setPatients)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setSelected('');
    onSelect(null);
    fetchPatients();
  }, [physicianId]);

  const handleChange = (patientId: string) => {
    setSelected(patientId);
    const pat = patients.find(p => p.patient_id === patientId) || null;
    onSelect(pat);
  };

  const handleCreatePatient = async () => {
    setSaving(true);
    try {
      const result = await createPatient({
        first_name: firstName,
        last_name: lastName,
        dob,
        insurance_provider: insuranceProvider,
        insurance_id: insuranceId,
        address,
        phone,
        physician_id: physicianId,
      });
      setShowForm(false);
      resetForm();
      fetchPatients();
      setSelected(result.patient_id);
      onSelect(result);
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setFirstName('');
    setLastName('');
    setDob('');
    setInsuranceProvider('medi-cal');
    setInsuranceId('');
    setAddress('');
    setPhone('');
  };

  if (!physicianId) {
    return (
      <div>
        <label className="pi-label text-xs mb-1.5 block">Patient</label>
        <select disabled className="pi-input text-sm">
          <option>Select a physician first</option>
        </select>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-end gap-2 mb-1">
        <div className="flex-1">
          <label className="pi-label text-xs mb-1.5 block">Patient</label>
          <select
            value={selected}
            onChange={e => handleChange(e.target.value)}
            className="pi-input text-sm"
            disabled={loading}
          >
            <option value="">{loading ? 'Loading...' : 'Select a patient'}</option>
            {patients.map(pat => (
              <option key={pat.patient_id} value={pat.patient_id}>
                {pat.first_name} {pat.last_name} — DOB: {pat.dob} — {pat.insurance_provider}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(!showForm)}
          className="pi-btn-secondary text-sm whitespace-nowrap"
        >
          {showForm ? 'Cancel' : '+ New Patient'}
        </button>
      </div>

      {showForm && (
        <div className="border border-pi-border-card p-4 space-y-3 mt-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="pi-label text-xs mb-1.5 block">First Name</label>
              <input type="text" value={firstName} onChange={e => setFirstName(e.target.value)} className="pi-input text-sm" />
            </div>
            <div>
              <label className="pi-label text-xs mb-1.5 block">Last Name</label>
              <input type="text" value={lastName} onChange={e => setLastName(e.target.value)} className="pi-input text-sm" />
            </div>
          </div>
          <div>
            <label className="pi-label text-xs mb-1.5 block">Date of Birth</label>
            <input type="date" value={dob} onChange={e => setDob(e.target.value)} className="pi-input text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="pi-label text-xs mb-1.5 block">Insurance Provider</label>
              <select value={insuranceProvider} onChange={e => setInsuranceProvider(e.target.value)} className="pi-input text-sm">
                <option value="medi-cal">Medi-Cal</option>
                <option value="medicare">Medicare</option>
                <option value="blue-cross">Blue Cross</option>
                <option value="aetna">Aetna</option>
                <option value="cigna">Cigna</option>
                <option value="united">United Healthcare</option>
              </select>
            </div>
            <div>
              <label className="pi-label text-xs mb-1.5 block">Insurance ID</label>
              <input type="text" value={insuranceId} onChange={e => setInsuranceId(e.target.value)} className="pi-input text-sm" placeholder="MC-12345" />
            </div>
          </div>
          <div>
            <label className="pi-label text-xs mb-1.5 block">Address</label>
            <input type="text" value={address} onChange={e => setAddress(e.target.value)} className="pi-input text-sm" />
          </div>
          <div>
            <label className="pi-label text-xs mb-1.5 block">Phone</label>
            <input type="text" value={phone} onChange={e => setPhone(e.target.value)} className="pi-input text-sm" />
          </div>
          <button
            type="button"
            onClick={handleCreatePatient}
            disabled={saving || !firstName || !lastName || !dob || !insuranceId}
            className="pi-btn-primary w-full py-2 text-sm"
          >
            {saving ? 'Creating...' : 'Create Patient'}
          </button>
        </div>
      )}
    </div>
  );
}
