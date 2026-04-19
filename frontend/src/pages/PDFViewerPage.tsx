import { useParams, useNavigate } from 'react-router-dom';
import PDFViewer from '../components/PDFViewer';
import { getDocumentUrl } from '../api/client';

export default function PDFViewerPage() {
  const { paRequestId, attemptHash, docNumber } = useParams<{
    paRequestId: string;
    attemptHash: string;
    docNumber: string;
  }>();
  const navigate = useNavigate();

  const url = getDocumentUrl(
    paRequestId || '',
    attemptHash || '',
    parseInt(docNumber || '0', 10)
  );

  const handleBack = () => {
    navigate(`/pa/${paRequestId}?from=pipeline`);
  };

  return <PDFViewer url={url} onBack={handleBack} />;
}
