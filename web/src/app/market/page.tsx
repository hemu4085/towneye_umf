import BackendReportPage from "@/components/reports/BackendReportPage";

export default function MarketPage() {
  return (
    <BackendReportPage
      title="Market & Appraisal Memo"
      badge="Pro Forma"
      description="Submarket comps, assessed vs. market value context, expansion economics, and sensitivity — full pro forma from the TownEye engine."
      reportType="proforma"
    />
  );
}
