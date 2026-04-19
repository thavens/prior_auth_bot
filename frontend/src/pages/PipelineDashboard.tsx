import { useState } from 'react';
import { Link } from 'react-router-dom';
import PipelineVisualizer from '../components/PipelineVisualizer';
import PASearch from '../components/PASearch';
import AWSHealth from '../components/AWSHealth';
import { AWSHealthResponse } from '../types';

export default function PipelineDashboard() {
  const [healthData, setHealthData] = useState<AWSHealthResponse | null>(null);

  return (
    <div>
      <nav className="pi-nav px-6">
        <div className="max-w-pi mx-auto w-full flex items-center justify-between">
          <h1 className="font-mono text-lg font-semibold tracking-tight text-pi-text">Pipeline Dashboard</h1>
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="pi-btn-secondary text-sm"
            >
              Physician Dashboard
            </Link>
            <Link
              to="/insurer"
              className="pi-btn-secondary text-sm"
            >
              Insurer Portal
            </Link>
          </div>
        </div>
      </nav>

      <main className="max-w-pi mx-auto px-6 py-16 space-y-12">
        <PipelineVisualizer healthData={healthData} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            <PASearch fromPage="pipeline" />
          </div>
          <div>
            <AWSHealth onHealthData={setHealthData} />
          </div>
        </div>
      </main>
    </div>
  );
}
