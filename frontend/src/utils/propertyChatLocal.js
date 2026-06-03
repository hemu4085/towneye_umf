/**
 * Rule-based property Q&A when the API is unreachable (demo-safe fallback).
 */

export function answerPropertyQuestionLocal(question, parcel) {
  const q = (question || '').toLowerCase().trim();
  const addr = parcel?.address || 'this property';
  const pid = parcel?.parcel_id || '';

  if (/adu|accessory|in-?law/.test(q)) {
    return (
      `For **${addr}**${pid ? ` (parcel ${pid})` : ''}: ADU and accessory-dwelling rules depend on your ` +
      `base zoning district and any overlays. TownEye checks permitted-use tables in the Gold zoning stack — ` +
      `generate the **Buildability Brief** or **Full Property Report** for this parcel's specific ADU signals. ` +
      `Always confirm with Arlington Building & Zoning before design work.`
    );
  }

  if (/by-?right|byright/.test(q)) {
    return (
      `**By-right** means a use or structure may proceed without a special permit, variance, or zoning relief ` +
      `when it fully conforms to the zoning code. If a project (addition, ADU, new use) is not allowed by-right, ` +
      `you typically need special permit, variance, or other approval.\n\n` +
      `For **${addr}**, open the **Buildability Brief** in TownEye for the parcel zoning verdict and development options.`
    );
  }

  if (/zoning|verdict|zone\b/.test(q)) {
    return (
      `Zoning for **${addr}** comes from TownEye's GIS + municipal zoning layers (base district + overlays). ` +
      `Choose **Buildability Brief** or **Full Property Report** to see the headline verdict and permitted-use stack for this parcel.`
    );
  }

  if (/flood|wetland|historic|constraint/.test(q)) {
    return (
      `Flood, wetland, and historic constraints for **${addr}** are summarized in TownEye's **Risk & Constraints** ` +
      `section. Generate that report (or the Full Property Report) for overlay flags tied to this parcel.`
    );
  }

  if (/far\b|floor area|stories|height/.test(q)) {
    return (
      `Buildable area (FAR, height, setbacks) for **${addr}** is computed in the **Buildability Brief**. ` +
      `Generate that report for indicative envelope numbers from TownEye Gold data.`
    );
  }

  return (
    `TownEye has assessor, zoning, and constraint data for **${addr}**. ` +
    `Try questions about ADU, by-right, zoning verdict, or flood/historic constraints — ` +
    `or generate a **Buildability** / **Full Property** report for parcel-specific detail.`
  );
}
