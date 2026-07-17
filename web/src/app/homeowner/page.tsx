import BackendReportPage from "@/components/reports/BackendReportPage";

export default function HomeownerPage() {
  return (
    <BackendReportPage
      title="Homeowner Insights"
      badge="Home"
      description="Assessed vs ZIP ZHVI, tax portal, open permits, zoning disclosures, and renovation permit paths — no fake ROI."
      reportType="homeowner"
    />
  );
}
