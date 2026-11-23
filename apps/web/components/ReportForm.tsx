"use client";

import { useState } from "react";
import { fitWithin, PHOTO_MAX_BYTES } from "@/lib/photo";

type Spot = { lat: number; lon: number; accuracy: number };

// Redraw the photo at 1280 px on its longest side as a JPEG. A canvas carries no EXIF, so the phone's
// location tags and camera details never leave the device.
async function shrink(file: File): Promise<Blob> {
  const img = await createImageBitmap(file, { imageOrientation: "from-image" });
  const { width, height } = fitWithin(img.width, img.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d")!.drawImage(img, 0, 0, width, height);
  img.close();
  for (const quality of [0.82, 0.6]) {
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", quality));
    if (blob && blob.size <= PHOTO_MAX_BYTES) return blob;
  }
  throw new Error("photo too large");
}

// The resident's report form: what they saw, an optional note and photo, and their position if they
// share it (required where there is no site). Posts to /api/report; works as a plain form without JavaScript.
export default function ReportForm({ siteId, kinds }: { siteId?: string; kinds: Record<string, string> }) {
  const needPlace = !siteId;
  const [spot, setSpot] = useState<Spot | null>(null);
  const [where, setWhere] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function locate() {
    if (!navigator.geolocation) return setWhere("This browser cannot share a location.");
    setWhere("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setSpot({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy });
        setWhere(`Location shared, accurate to about ${Math.round(p.coords.accuracy)} m.`);
      },
      () => setWhere("Location is off. Allow it for this page in your browser, then try again."),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 },
    );
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (needPlace && !spot) return setMessage("Please share your location, so the officer can find the place.");
    const data = new FormData(e.currentTarget);
    const file = data.get("photo");
    setBusy(true);
    setMessage(null);
    if (file instanceof File && file.size > 0) {
      try {
        data.set("photo", await shrink(file), "photo.jpg");
      } catch {
        setBusy(false);
        return setMessage("That photo could not be read. Please pick another one.");
      }
    } else {
      data.delete("photo");
    }
    const res = await fetch("/api/report", { method: "POST", body: data, headers: { Accept: "application/json" } }).catch(() => null);
    if (res?.ok) return window.location.assign(`${window.location.pathname}?r=sent`);
    const body = await res?.json().catch(() => null);
    setMessage(body?.message ?? "The report could not be sent. Please check your connection and try again.");
    setBusy(false);
  }

  return (
    <form method="post" action="/api/report" encType="multipart/form-data" className="outcome" onSubmit={submit}>
      {siteId && <input type="hidden" name="site_id" value={siteId} />}
      <input type="text" name="website" tabIndex={-1} autoComplete="off" className="hp" aria-hidden="true" />
      {spot && (
        <>
          <input type="hidden" name="lat" value={spot.lat} />
          <input type="hidden" name="lon" value={spot.lon} />
          <input type="hidden" name="accuracy" value={spot.accuracy} />
        </>
      )}
      <fieldset>
        <legend className="small muted">What did you see?</legend>
        {Object.entries(kinds).map(([k, label]) => (
          <label key={k} className="choice"><input type="radio" name="kind" value={k} required /> {label}</label>
        ))}
      </fieldset>
      <textarea name="note" rows={3} maxLength={500} placeholder="Anything else? (optional, no names or phone numbers please)" />
      <label className="field">
        <span className="small muted">Photo of the dust or the site (optional)</span>
        <input type="file" name="photo" accept="image/*" />
      </label>
      <div className="field">
        <span className="small muted">{needPlace ? "Where is it? Stand near the place and share your location." : "Your location (optional): helps the officer find the exact spot."}</span>
        <button type="button" className="btn" onClick={locate}>{spot ? "Update my location" : "Share my location"}</button>
        {where && <span className="small" role="status">{where}</span>}
      </div>
      {message && <div className="banner" role="alert">{message}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Sending…" : "Send report"}</button>
    </form>
  );
}
