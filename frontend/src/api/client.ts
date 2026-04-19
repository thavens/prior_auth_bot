import axios from 'axios';
import { InsurerQueueItem, PARequest, InsurerDecision } from '../types';

const api = axios.create({ baseURL: '/api' });

export const searchPARequests = (patient?: string, physician?: string) =>
  api.get('/pa-requests', { params: { patient, physician } }).then(r => r.data.results);

export const getPARequest = (id: string) =>
  api.get(`/pa-requests/${id}`).then(r => r.data);

export const getDocumentUrl = (paRequestId: string, attemptHash: string, docNumber: number) =>
  `/api/pa-requests/${paRequestId}/documents/${attemptHash}/${docNumber}`;

export const getAWSHealth = () =>
  api.get('/aws/health').then(r => r.data);

export const createPARequest = (formData: FormData) =>
  api.post('/pa-requests', formData).then(r => r.data);

export const getPatients = (physicianId?: string, q?: string) =>
  api.get('/patients', { params: { physician_id: physicianId, q } }).then(r => r.data.patients);

export const createPatient = (payload: Record<string, string>) =>
  api.post('/patients', payload).then(r => r.data);

export const getPhysicians = (q?: string) =>
  api.get('/physicians', { params: { q } }).then(r => r.data.physicians);

export const seedForms = () =>
  api.post('/seed-forms').then(r => r.data);

export const getInsurerQueue = (): Promise<InsurerQueueItem[]> =>
  api.get('/insurer/queue').then(r => r.data.queue);

export const getInsurerPARequest = (id: string): Promise<PARequest> =>
  api.get(`/insurer/pa-requests/${id}`).then(r => r.data);

export const submitInsurerDecision = (id: string, decision: InsurerDecision) =>
  api.post(`/insurer/pa-requests/${id}/decide`, decision).then(r => r.data);

export const connectWebSocket = (onMessage: (data: any) => void): WebSocket => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/pa-status`);
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      // ignore non-JSON messages
    }
  };
  ws.onerror = () => {
    // silently handle connection errors; polling fallback keeps data fresh
  };
  return ws;
};
