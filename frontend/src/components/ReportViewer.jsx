import { absoluteUrl } from '../utils/share';
import { extractReportBody, extractReportStyles } from '../utils/reportHtml';
import { Download, Link as LinkIcon } from 'lucide-react';

const SHELL_CSS = `
  .towneye-report-shell {
    width: 100%;
    max-width: none;
    box-sizing: border-box;
    font-family: 'Inter', system-ui, sans-serif;
    color: #0f172a;
    background: #ffffff;
  }
  .towneye-report-shell .te-report {
    width: 100%;
    max-width: none;
    padding: 2rem;
  }
  .towneye-report-shell * {
    box-sizing: border-box;
  }
  .towneye-report-shell h1, .towneye-report-shell h2, .towneye-report-shell h3 {
    font-family: 'Inter', system-ui, sans-serif;
    letter-spacing: -0.025em;
  }
`;

export default function ReportViewer({ html, downloadUrl, onShare, shareNotice }) {
  const pdfHref = downloadUrl ? absoluteUrl(downloadUrl) : null;
  const reportStyles = extractReportStyles(html);
  const reportBody = extractReportBody(html);

  return (
    <div className="w-full flex flex-col items-center">
      {/* Viewer Action Bar */}
      <div className="w-full flex items-center justify-end gap-3 mb-6">
        {shareNotice && (
          <span className="text-xs font-mono text-emerald-400 bg-emerald-400/10 px-3 py-1.5 rounded-full border border-emerald-400/20 mr-2">
            {shareNotice}
          </span>
        )}
        <button 
          type="button" 
          onClick={onShare} 
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 border border-slate-700 hover:border-slate-600 hover:bg-slate-700 text-slate-200 rounded-lg text-sm font-medium transition-colors"
          disabled={!pdfHref}
        >
          <LinkIcon className="w-4 h-4" />
          Share Link
        </button>
        {pdfHref ? (
          <a 
            href={pdfHref} 
            download 
            className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-brand-500/20"
          >
            <Download className="w-4 h-4" />
            Download PDF
          </a>
        ) : (
          <span className="flex items-center gap-2 px-4 py-2 bg-slate-800/50 border border-slate-800 text-slate-500 rounded-lg text-sm font-medium cursor-not-allowed">
            <Download className="w-4 h-4" />
            PDF Export Unavailable
          </span>
        )}
      </div>

      {/* The Report Frame */}
      <div className="w-full max-w-5xl bg-white rounded-xl shadow-2xl shadow-black/50 overflow-hidden ring-1 ring-slate-800">
        {/* Mock OS Window Chrome to make it look like a document viewer */}
        <div className="h-10 bg-slate-100 border-b border-slate-200 flex items-center px-4 gap-2">
          <div className="w-3 h-3 rounded-full bg-slate-300"></div>
          <div className="w-3 h-3 rounded-full bg-slate-300"></div>
          <div className="w-3 h-3 rounded-full bg-slate-300"></div>
          <div className="mx-auto text-xs font-mono text-slate-400 font-medium">DOCUMENT_VIEWER_V2</div>
        </div>
        
        {/* Rendered HTML */}
        <div className="w-full overflow-x-auto min-h-[600px]">
          <style>{SHELL_CSS}</style>
          {reportStyles ? <style>{reportStyles}</style> : null}
          <div
            className="towneye-report-shell w-full"
            dangerouslySetInnerHTML={{ __html: reportBody }}
          />
        </div>
      </div>
    </div>
  );
}