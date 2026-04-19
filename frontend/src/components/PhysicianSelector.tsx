import { useState, useEffect } from 'react';
import { getPhysicians } from '../api/client';
import { PhysicianRecord } from '../types';

interface Props {
  onSelect: (physician: PhysicianRecord | null) => void;
}

export default function PhysicianSelector({ onSelect }: Props) {
  const [physicians, setPhysicians] = useState<PhysicianRecord[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPhysicians()
      .then(setPhysicians)
      .finally(() => setLoading(false));
  }, []);

  const handleChange = (physicianId: string) => {
    setSelected(physicianId);
    const doc = physicians.find(p => p.physician_id === physicianId) || null;
    onSelect(doc);
  };

  return (
    <div>
      <label className="pi-label text-xs mb-1.5 block">Physician</label>
      <select
        value={selected}
        onChange={e => handleChange(e.target.value)}
        className="pi-input text-sm"
        disabled={loading}
      >
        <option value="">{loading ? 'Loading...' : 'Select a physician'}</option>
        {physicians.map(doc => (
          <option key={doc.physician_id} value={doc.physician_id}>
            Dr. {doc.first_name} {doc.last_name} — {doc.specialty || 'General'}
          </option>
        ))}
      </select>
    </div>
  );
}
