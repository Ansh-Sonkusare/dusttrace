// The honesty notice on the overview when a run isn't fully live. Pure, unit-tested.
import { dayShort, hhmm } from "./format";

export function dataNotice(mode: string, newestReal: string | null | undefined, issuedAt: string,
                           filledStations = 0): string | null {
  if (mode === "live") return null;
  if (newestReal) {
    const days = Math.floor((new Date(issuedAt).getTime() - new Date(newestReal).getTime()) / 86_400_000);
    if (filledStations > 0) {
      return `The forecast uses ${filledStations} real CPCB stations. Their feed through OpenAQ stopped at ${dayShort(newestReal)}, `
        + `${hhmm(newestReal)}${days >= 1 ? ` (${days} ${days === 1 ? "day" : "days"} ago)` : ""}, so the hours since are filled from `
        + "Copernicus CAMS, corrected against each station's own history. Filled hours are less accurate than measured ones "
        + "(see the Forecast page); nothing filled is stored as a reading.";
    }
    if (days >= 1) {
      return `Real station readings stop at ${dayShort(newestReal)}, ${hhmm(newestReal)} (${days} ${days === 1 ? "day" : "days"} ago): `
        + "the CPCB feed through OpenAQ is behind. Until it catches up, the forecast starts from labelled sample stations "
        + "driven by the live weather. Treat the numbers as a demonstration.";
    }
  }
  return `This run uses ${mode === "mixed" ? "partly " : ""}synthetic readings or weather because the live sources were unreachable. `
    + "Treat the numbers as a demonstration until the live ingest runs.";
}
