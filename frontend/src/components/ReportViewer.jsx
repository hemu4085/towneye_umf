import { absoluteUrl } from '../utils/share';
import { extractReportBody, extractReportStyles } from '../utils/reportHtml';

const SHELL_CSS = `
  .towneye-report-shell {
    width: 100%;
    max-width: none;
    box-sizing: border-box;
    font-family: 'DM Sans', Arial, sans-serif;
    color: #0B1F3A;
  }
  .towneye-report-shell .te-report {
    width: 100%;
    max-width: none;
  }
  .towneye-report-shell * {
    box-sizing: border-box;
  }
`;

export default function ReportViewer({ html, downloadUrl, onShare, shareNotice }) {
  const pdfHref = downloadUrl ? absoluteUrl(downloadUrl) : null;
  const reportStyles = extractReportStyles(html);
  const reportBody = extractReportBody(html);

  return (
    <div className="mt-8 w-full">
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
      <div className="bg-white rounded-xl shadow-xl text-navy report-frame w-full overflow-x-auto">
        <style>{SHELL_CSS}</style>
        {reportStyles ? <style>{reportStyles}</style> : null}
        <div
          className="towneye-report-shell w-full"
          dangerouslySetInnerHTML={{ __html: reportBody }}
        />
      </div>
    </div>
  );
}
