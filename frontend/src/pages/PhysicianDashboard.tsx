import { Link } from 'react-router-dom';
import AudioUpload from '../components/AudioUpload';
import PASearch from '../components/PASearch';

export default function PhysicianDashboard() {
  return (
    <div>
      <nav className="pi-nav px-6">
        <div className="max-w-pi mx-auto w-full flex items-center justify-between">
          <h1 className="font-mono text-lg font-semibold tracking-tight text-pi-text">Physician Dashboard</h1>
          <div className="flex items-center gap-3">
            <Link
              to="/insurer"
              className="pi-btn-secondary text-sm"
            >
              Insurer Portal
            </Link>
            <Link
              to="/pipeline"
              className="pi-btn-secondary text-sm"
            >
              Pipeline Dashboard
            </Link>
          </div>
        </div>
      </nav>

      <main className="max-w-pi mx-auto px-6 py-16 space-y-12">
        <AudioUpload />
        <PASearch fromPage="physician" />
      </main>
    </div>
  );
}
