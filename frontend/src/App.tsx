import { BrowserRouter, Routes, Route } from 'react-router-dom';
import PipelineDashboard from './pages/PipelineDashboard';
import PhysicianDashboard from './pages/PhysicianDashboard';
import PAVisualizerPage from './pages/PAVisualizerPage';
import PDFViewerPage from './pages/PDFViewerPage';
import InsurerDashboard from './pages/InsurerDashboard';
import InsurerReviewPage from './pages/InsurerReviewPage';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-pi-bg font-sans">
      <Routes>
        <Route path="/" element={<PhysicianDashboard />} />
        <Route path="/pipeline" element={<PipelineDashboard />} />
        <Route path="/pa/:paRequestId" element={<PAVisualizerPage />} />
        <Route path="/pa/:paRequestId/pdf/:attemptHash/:docNumber" element={<PDFViewerPage />} />
        <Route path="/insurer" element={<InsurerDashboard />} />
        <Route path="/insurer/review/:paRequestId" element={<InsurerReviewPage />} />
      </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
