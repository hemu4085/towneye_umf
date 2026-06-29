"use client";

import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import type { DealRadarDeal } from "@/lib/api";

const ARLINGTON_CENTER: [number, number] = [42.4154, -71.1565];

/**
 * Google Maps–style palette (Material / Maps brand colors).
 * Base tiles: Esri World Street — light land, pale water, soft green parks, readable road hierarchy.
 * (Same visual language as Google Maps; no Google API key required.)
 */
const GOOGLE = {
  land: "#e8e4df",
  red: "#ea4335",
  blue: "#1a73e8",
  green: "#34a853",
  purple: "#9334e6",
  stroke: "#ffffff",
  strokeSelected: "#b31412",
} as const;

/** Esri World Street Map — closest free raster match to Google Maps road view */
const MAP_TILES =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}";

const MAP_ATTRIBUTION =
  '&copy; <a href="https://www.esri.com/">Esri</a> &mdash; TomTom, USGS, OpenStreetMap contributors';

function markerFill(signals: string[] = [], highlighted: boolean) {
  if (highlighted) return GOOGLE.red;
  if (signals.includes("by_right_multifamily")) return GOOGLE.purple;
  if (signals.includes("entity_owner")) return GOOGLE.green;
  return GOOGLE.blue;
}

function FitBounds({ deals }: { deals: DealRadarDeal[] }) {
  const map = useMap();
  const boundsKey = useMemo(
    () => deals.map((d) => `${d.rank}:${d.lat}:${d.lng}`).join("|"),
    [deals],
  );

  useEffect(() => {
    const points = deals
      .filter((d) => d.lat != null && d.lng != null)
      .map((d) => [d.lat as number, d.lng as number] as [number, number]);

    if (points.length === 0) {
      map.setView(ARLINGTON_CENTER, 13.5);
      return;
    }
    if (points.length === 1) {
      map.setView(points[0], 15);
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [56, 56], maxZoom: 15 });
  }, [boundsKey, deals, map]);

  return null;
}

function InvalidateSize({ visible }: { visible: boolean }) {
  const map = useMap();

  useEffect(() => {
    if (!visible) return;
    const id = window.setTimeout(() => {
      map.invalidateSize({ animate: false });
    }, 80);
    return () => window.clearTimeout(id);
  }, [visible, map]);

  return null;
}

type RadarMapProps = {
  townSlug: string;
  deals?: DealRadarDeal[];
  highlightParcelId?: string | null;
  highlightRank?: number | null;
  visible?: boolean;
  onSelectDeal?: (deal: DealRadarDeal) => void;
};

export default function RadarMap({
  townSlug,
  deals = [],
  highlightParcelId,
  highlightRank,
  visible = true,
  onSelectDeal,
}: RadarMapProps) {
  const [clientReady, setClientReady] = useState(false);
  const mappable = deals.filter((d) => d.lat != null && d.lng != null);

  useEffect(() => {
    let cancelled = false;
    const id = requestAnimationFrame(() => {
      if (!cancelled) setClientReady(true);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(id);
      setClientReady(false);
    };
  }, []);

  if (!clientReady) {
    return (
      <div
        className="w-full h-full min-h-[240px] flex items-center justify-center text-[#5f6368] text-sm"
        style={{ background: GOOGLE.land }}
      >
        Loading map…
      </div>
    );
  }

  return (
    <div className="towneye-radar-map towneye-radar-map--google w-full h-full relative">
      <MapContainer
        key={`deal-radar-map-${townSlug}`}
        center={ARLINGTON_CENTER}
        zoom={13.5}
        scrollWheelZoom
        className="w-full h-full z-0"
        style={{ background: GOOGLE.land, minHeight: "100%" }}
      >
        <TileLayer attribution={MAP_ATTRIBUTION} url={MAP_TILES} maxZoom={19} />
        <InvalidateSize visible={visible} />
        <FitBounds deals={mappable} />
        {mappable.map((deal, index) => {
          const highlighted =
            (highlightRank != null && deal.rank === highlightRank) ||
            (highlightParcelId != null && deal.parcel_id === highlightParcelId);
          const fill = markerFill(deal.signals, highlighted);
          const radius = highlighted ? 9 : 6;

          return (
            <CircleMarker
              key={`${deal.rank ?? index}-${deal.parcel_id}`}
              center={[deal.lat as number, deal.lng as number]}
              radius={radius}
              pathOptions={{
                color: highlighted ? GOOGLE.strokeSelected : GOOGLE.stroke,
                weight: highlighted ? 2.5 : 2,
                fillColor: fill,
                fillOpacity: 1,
                opacity: 1,
              }}
              eventHandlers={{
                click: () => onSelectDeal?.(deal),
              }}
            >
              <Popup>
                <div className="font-sans text-sm min-w-[180px]">
                  <div className="font-medium text-[#202124] leading-snug">{deal.address}</div>
                  <div className="text-[#5f6368] mt-1.5 text-xs">
                    Score <strong className="text-[#202124]">{deal.score ?? "—"}</strong> ·{" "}
                    {deal.zone_code || "—"}
                  </div>
                  <div className="text-[#5f6368] text-xs mt-1">
                    +{deal.expansion_room_sqft?.toLocaleString() ?? "—"} sf ·{" "}
                    {deal.tenure_years ?? "—"} yr tenure
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      {deals.length > 0 && mappable.length === 0 && (
        <div className="absolute top-3 left-3 right-3 z-[500] bg-white border border-[#dadce0] text-[#202124] text-xs px-3 py-2 rounded-lg shadow-md">
          Results loaded but coordinates are missing — restart the API (
          <code className="text-[10px]">./start_demo.sh</code>).
        </div>
      )}

      {mappable.length > 0 && (
        <div className="absolute top-3 left-3 z-[500] bg-white text-[#202124] text-xs font-medium px-3 py-1.5 rounded-full shadow-md border border-[#dadce0]">
          {mappable.length} on map
        </div>
      )}
    </div>
  );
}
