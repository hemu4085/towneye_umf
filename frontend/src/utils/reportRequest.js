export function buildReportRequestMailto(report, address, adminEmail, parcel = null) {
  const subject = encodeURIComponent(`TownEye Report Request: ${report.name}`);
  const lines = [
    'Hello TownEye,',
    '',
    'Please generate the following report for me:',
    '',
    `Report: ${report.name}`,
    `Address: ${address}`,
  ];
  if (parcel?.parcel_id) lines.push(`Parcel ID: ${parcel.parcel_id}`);
  if (parcel?.town_name) lines.push(`Town: ${parcel.town_name}, MA`);
  lines.push('', 'Thank you.');
  const body = encodeURIComponent(lines.join('\n'));
  return `mailto:${adminEmail}?subject=${subject}&body=${body}`;
}
