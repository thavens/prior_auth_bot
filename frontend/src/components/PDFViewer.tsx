interface PDFViewerProps {
  url: string;
  onBack: () => void;
}

export default function PDFViewer({ url, onBack }: PDFViewerProps) {
  return (
    <div className="flex flex-col h-screen">
      <div className="pi-nav px-6 justify-between">
        <button
          onClick={onBack}
          className="pi-btn-secondary text-sm"
        >
          Back
        </button>
        <span className="pi-label">PA Document</span>
      </div>
      <iframe src={url} className="flex-1 w-full" />
    </div>
  );
}
