export interface PARequestSummary {
  pa_request_id: string;
  status: string;
  patient_name: string;
  physician_name: string;
  created_at: string;
  attempt_number: number;
}

export interface Patient {
  patient_id: string;
  first_name: string;
  last_name: string;
  dob: string;
  insurance_provider: string;
  insurance_id: string;
  address: string;
  phone: string;
}

export interface Physician {
  physician_id: string;
  first_name: string;
  last_name: string;
  npi: string;
  specialty: string;
  phone: string;
  fax: string;
}

export interface PARequest {
  pa_request_id: string;
  created_at: string;
  updated_at: string;
  status: string;
  patient: Patient;
  physician: Physician;
  audio_s3_key?: string;
  transcript?: string;
  entities?: any[];
  treatments_requiring_pa?: any[];
  selected_forms?: any[];
  memories?: any[];
  completed_form_s3_keys?: string[];
  submission_result?: any;
  outcome?: string;
  attempt_number: number;
  attempt_hash: string;
  rejection_history: any[];
  error?: string;
}

export interface PatientRecord extends Patient {
  primary_physician_id: string;
  created_at: string;
  updated_at: string;
}

export interface PhysicianRecord extends Physician {
  created_at: string;
  updated_at: string;
}

export interface PatientCreatePayload {
  first_name: string;
  last_name: string;
  dob: string;
  insurance_provider: string;
  insurance_id: string;
  address: string;
  phone: string;
  physician_id: string;
}

export interface AWSComponent {
  name: string;
  type: string;
  status: 'healthy' | 'error';
  error?: string;
}

export interface AWSHealthResponse {
  overall: string;
  components: AWSComponent[];
  checked_at: string;
}

export interface StatusUpdate {
  type: string;
  pa_request_id: string;
  status: string;
  updated_at: string;
  patient_name: string;
}

export interface InsurerDecision {
  pa_request_id: string;
  decision: 'approved' | 'rejected';
  rejection_reasons: string[];
  feedback: string;
}

export interface InsurerQueueItem {
  pa_request_id: string;
  status: string;
  patient_name: string;
  physician_name: string;
  insurance_provider: string;
  treatment_text: string;
  created_at: string;
  attempt_number: number;
}
