import { absoluteUrl } from '../utils/share';

export default function ReportViewer({ html, downloadUrl, onShare, shareNotice }) {
  const pdfHref = downloadUrl ? absoluteUrl(downloadUrl) : null;

  return (
    <div className="mt-8">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {pdfHref ? (
          <a href={pdfHref} download className="btn-gold inline-block no-underline">
            Download PDF
          </a>
        ) : (
          <span className="text-sm text-graytown">PDF export available on production tier</span>
        )}
        <button type="button" onClick={onShare} className="btn-outline" disabled={!pdfHref}>
          Share Link
        </button>
        {shareNotice && <span className="text-sm text-gold">{shareNotice}</span>}
      </div>
      <div
        className="bg-white rounded-xl overflow-hidden shadow-xl text-navy report-frame"
        style={{ minHeight: 400 }}
      >
        <iframe
          title="Report preview"
          srcDoc={html}
          className="w-full border-0"
          style={{ minHeight: '70vh' }}
          sandbox="allow-same-origin"
        />
      </div>
    </div>
  );
}
