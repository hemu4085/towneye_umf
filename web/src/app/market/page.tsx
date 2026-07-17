import BackendReportPage from "@/components/reports/BackendReportPage";

export default function MarketPage() {
  return (
    <BackendReportPage
      title="Market Trend Report"
      badge="Market"
      description="ZIP-level ZHVI trends from TownEye Gold, assessor context, and honest comps coverage — directional diligence, not an appraisal."
      reportType="market"
    />
  );
}
