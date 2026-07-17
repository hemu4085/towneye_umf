import BackendReportPage from "@/components/reports/BackendReportPage";

export default function LenderPage() {
  return (
    <BackendReportPage
      title="Lender Risk Report"
      badge="Underwriting Pack"
      description="Full collateral memo: flood, violations, permits, title-adjacent flags, and lender checklist — generated from Gold data and town ISD records."
      reportType="lender"
    />
  );
}
