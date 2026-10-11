"use client";

import { useMemo, useState } from "react";
import type { FcPoint, ObsPoint } from "@/lib/queries";
import { dayHour, hhmm, istHour } from "@/lib/format";

const W = 1000, H = 340, L = 52, R = 24, T = 18, B = 40;
const AMBER = "#C27F26", OBS = "#8E8E94", GRID = "#25252A", INK = "#F2F2F2", MUTED = "#8E8E94";

export default function ForecastChart({ fc, obs, threshold = 100 }: { fc: FcPoint[]; obs: ObsPoint[]; threshold?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = useMemo(() => {
    const all = [...obs.map((o) => ({ ts: o.ts, kind: "obs" as const, v: o.pm10 })), ...fc.map((f) => ({ ts: f.ts, kind: "fc" as const, v: f.pm10 }))];
    return all.sort((a, b) => a.ts.localeCompare(b.ts));
  }, [fc, obs]);
  if (!fc.length) return <div className="empty">No forecast yet.</div>;

  const t0 = new Date(pts[0].ts).getTime();
  const t1 = new Date(pts[pts.length - 1].ts).getTime();
  const ymax = Math.max(threshold * 1.4, ...fc.map((f) => f.pm10_hi), ...obs.map((o) => o.pm10)) * 1.08;
  const x = (ts: string) => L + ((new Date(ts).getTime() - t0) / (t1 - t0 || 1)) * (W - L - R);
  const y = (v: number) => T + (H - T - B) * (1 - v / ymax);
  const step = ymax > 300 ? 100 : 50;
  const ticks = Array.from({ length: Math.floor(ymax / step) + 1 }, (_, k) => k * step);
  const line = (arr: { ts: string; v: number }[]) => arr.map((p, k) => `${k ? "L" : "M"}${x(p.ts).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
  const band = `M${fc.map((f) => `${x(f.ts).toFixed(1)} ${y(f.pm10_hi).toFixed(1)}`).join(" L")} L${[...fc].reverse().map((f) => `${x(f.ts).toFixed(1)} ${y(f.pm10_lo).toFixed(1)}`).join(" L")}Z`;
  const peak = fc.reduce((a, b) => (b.pm10 > a.pm10 ? b : a));
  const xLabels = pts.filter((p) => istHour(p.ts) % 6 === 0 && new Date(p.ts).getUTCMinutes() === 30);
  const hv = hover !== null ? fc[hover] : null;

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity;
    fc.forEach((f, k) => { const d = Math.abs(x(f.ts) - px); if (d < bd) { bd = d; best = k; } });
    setHover(px >= x(fc[0].ts) - 10 ? best : null);
  }

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        role="img" aria-label={`PM10 forecast for the next ${fc.length} hours; peak ${Math.round(peak.pm10)} at ${dayHour(peak.ts)}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={GRID} />
            <text x={L - 10} y={y(t) + 4} textAnchor="end" fontSize="12" fill={MUTED}>{t}</text>
          </g>
        ))}
        {xLabels.map((p) => (
          <text key={p.ts} x={x(p.ts)} y={H - 14} textAnchor="middle" fontSize="12" fill={MUTED}>{istHour(p.ts) === 0 ? dayHour(p.ts) : hhmm(p.ts)}</text>
        ))}
        <line x1={x(fc[0].ts)} x2={x(fc[0].ts)} y1={T} y2={H - B} stroke={INK} strokeOpacity=".3" />
        <text x={x(fc[0].ts) + 6} y={T + 12} fontSize="12" fill="#C9C9CD">Now</text>
        <path d={band} fill={AMBER} opacity=".14" />
        <line x1={L} x2={W - R} y1={y(threshold)} y2={y(threshold)} stroke={INK} strokeOpacity=".5" strokeWidth="1.5" />
        <text x={L + 8} y={y(threshold) - 6} fontSize="12" fill={INK} opacity=".85">National 24-h standard, {threshold}</text>
        {obs.length > 0 && <path d={line(obs.map((o) => ({ ts: o.ts, v: o.pm10 })))} fill="none" stroke={OBS} strokeWidth="2" strokeLinejoin="round" />}
        <path d={line(fc.map((f) => ({ ts: f.ts, v: f.pm10 })))} fill="none" stroke={AMBER} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(peak.ts)} cy={y(peak.pm10)} r="5" fill={AMBER} stroke="#141416" strokeWidth="2" />
        <text x={x(peak.ts) + 10} y={y(peak.pm10) - 8} fontSize="13" fontWeight="600" fill={INK}>Peak {Math.round(peak.pm10)} µg/m³, {dayHour(peak.ts)}</text>
        {hv && (
          <g pointerEvents="none">
            <line x1={x(hv.ts)} x2={x(hv.ts)} y1={T} y2={H - B} stroke={INK} strokeOpacity=".35" />
            <circle cx={x(hv.ts)} cy={y(hv.pm10)} r="5" fill={AMBER} stroke="#141416" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hv && (
        <div className="panel" style={{ position: "absolute", top: 8, right: 12, padding: "8px 12px", fontSize: 12.5, pointerEvents: "none" }}>
          <b>{dayHour(hv.ts)} IST</b><br />
          PM10 {Math.round(hv.pm10)} µg/m³ (likely {Math.round(hv.pm10_lo)}–{Math.round(hv.pm10_hi)})<br />
          Chance above {threshold}: {Math.round(hv.p_exceed * 100)}%
        </div>
      )}
      <div style={{ display: "flex", gap: 18, fontSize: 12.5, color: "var(--text-2)", padding: "4px 4px 0" }}>
        <span><i style={{ display: "inline-block", width: 18, height: 3, background: OBS, verticalAlign: 3, marginRight: 6 }} />Observed, station average</span>
        <span><i style={{ display: "inline-block", width: 18, height: 3, background: AMBER, verticalAlign: 3, marginRight: 6 }} />Forecast</span>
        <span><i style={{ display: "inline-block", width: 18, height: 10, background: AMBER, opacity: 0.25, verticalAlign: 0, marginRight: 6 }} />Likely range (10th–90th percentile)</span>
      </div>
    </div>
  );
}
