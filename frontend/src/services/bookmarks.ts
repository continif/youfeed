import { api } from "@/services/api";
import type { BookmarkIdsOut, BookmarkOut } from "@/types/api";

export async function listBookmarks(opts?: {
  limit?: number;
  offset?: number;
}): Promise<BookmarkOut[]> {
  const params = new URLSearchParams();
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return api
    .get(`yf_me/bookmarks${qs ? `?${qs}` : ""}`)
    .json<BookmarkOut[]>();
}

export async function addBookmark(articleId: number): Promise<BookmarkOut> {
  return api
    .post("yf_me/bookmarks", { json: { article_id: articleId } })
    .json<BookmarkOut>();
}

export async function removeBookmark(articleId: number): Promise<void> {
  await api.delete(`yf_me/bookmarks/${articleId}`);
}

export async function checkBookmarks(ids: number[]): Promise<BookmarkIdsOut> {
  return api
    .post("yf_me/bookmarks/check", { json: { ids } })
    .json<BookmarkIdsOut>();
}
