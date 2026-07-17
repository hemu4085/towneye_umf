import BackendReportPage from "@/components/reports/BackendReportPage";

export default function NeighborhoodPage() {
  return (
    <BackendReportPage
      title="Neighborhood Guide"
      badge="Area"
      description="Street assessor context, ZIP market pulse, transit alerts, school calendar, and capital projects — real Gold, no invented Walk Scores or school ratings."
      reportType="neighborhood"
    />
  );
}
