import { api } from "@/services/api";
import type {
  ArticleDetailOut,
  ArticleListOut,
  RelatedArticlesOut,
  RelatedFormula,
} from "@/types/api";

export async function fetchFeed(
  opts: {
    cursor?: string;
    limit?: number;
    category?: number;
    topic?: number;
  } = {},
): Promise<ArticleListOut> {
  const search = new URLSearchParams();
  if (opts.cursor) search.set("cursor", opts.cursor);
  if (opts.limit) search.set("limit", String(opts.limit));
  if (opts.category != null) search.set("category", String(opts.category));
  if (opts.topic != null) search.set("topic", String(opts.topic));
  const qs = search.toString();
  return api
    .get(`yf_articles/feed${qs ? `?${qs}` : ""}`)
    .json<ArticleListOut>();
}

export async function fetchArticle(id: number): Promise<ArticleDetailOut> {
  return api.get(`yf_articles/${id}`).json<ArticleDetailOut>();
}

export async function fetchRelatedArticles(
  id: number,
  opts: { formula?: RelatedFormula; days?: number; minOverlap?: number; limit?: number } = {},
): Promise<RelatedArticlesOut> {
  const search = new URLSearchParams();
  if (opts.formula) search.set("formula", opts.formula);
  if (opts.days != null) search.set("days", String(opts.days));
  if (opts.minOverlap != null) search.set("min_overlap", String(opts.minOverlap));
  if (opts.limit != null) search.set("limit", String(opts.limit));
  const qs = search.toString();
  return api
    .get(`yf_articles/${id}/related${qs ? `?${qs}` : ""}`)
    .json<RelatedArticlesOut>();
}
