import BackendReportPage from "@/components/reports/BackendReportPage";

export default function RealtorBriefPage() {
  return (
    <BackendReportPage
      title="Realtor Listing Brief"
      badge="Listing"
      description="Gold-backed listing memo — assessor facts, zoning angles, ZIP pricing context, and honest gaps for schools/MLS comps. Not a CMA."
      reportType="listing-brief"
    />
  );
}
