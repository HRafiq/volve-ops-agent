// Fetching, and nothing else.
//
// No client-side store, no cache, no derived state. Protocol section 21.1 says the console renders
// and does not compute, and a cache is where a figure quietly becomes stale while still carrying
// the source that vouched for it when it was fresh. Every screen asks for what it shows.

import type { Header, InvestigationDetail, Queue, ReviewHistory, SystemHealth } from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} from ${path}: ${body.slice(0, 200)}`);
  }
  return (await response.json()) as T;
}

export const fetchHeader = () => get<Header>("/api/header");
export const fetchQueue = () => get<Queue>("/api/production/queue");
export const fetchDetail = (id: string) =>
  get<InvestigationDetail>(`/api/investigations/${encodeURIComponent(id)}`);
export const fetchReview = (id: string) =>
  get<ReviewHistory>(`/api/investigations/${encodeURIComponent(id)}/review`);
export const fetchHealth = () => get<SystemHealth>("/api/system/health");
export const fetchFacts = (id: string) =>
  get<Record<string, unknown>[]>(`/api/investigations/${encodeURIComponent(id)}/facts`);

export async function postReview(
  id: string,
  action: string,
  actor: string,
  note?: string,
): Promise<ReviewHistory> {
  const route = action === "add_correction" ? "correction" : action.replace(/_/g, "-");
  const response = await fetch(`/api/review/${encodeURIComponent(id)}/${route}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ actor, note: note ?? null }),
  });
  if (!response.ok) {
    const body = (await response.json()) as { detail?: string };
    // 409 is the log refusing a second judgement on a settled finding, which is not an error in the
    // user's input and is worth surfacing in those words rather than as a generic failure.
    throw new Error(body.detail ?? `${response.status}`);
  }
  await response.json();
  return fetchReview(id);
}
