import { api } from "./api";
import type { SearchOut, SuggestOut } from "@/types/api";

export async function search(
  q: string,
  opts: { limit?: number; offset?: number } = {},
): Promise<SearchOut> {
  const params = new URLSearchParams({ q });
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  return api.get(`yf_search?${params.toString()}`).json<SearchOut>();
}

export async function suggest(q: string, limit = 8): Promise<SuggestOut> {
  if (!q || q.trim().length < 2) return { topics: [], sources: [] };
  const params = new URLSearchParams({ q: q.trim(), limit: String(limit) });
  return api.get(`yf_search/suggest?${params.toString()}`).json<SuggestOut>();
}
