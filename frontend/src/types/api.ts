// DTO types speculari agli schemas Pydantic backend (vedi backend/app/schemas/*).

export interface UserOut {
  id: number;
  username: string;
  email: string;
  email_verified: boolean;
  onboarding_completed_at: string | null;
  profile_seo_title: string | null;
  profile_seo_description: string | null;
  created_at: string;
}

export interface ArticleSourceMini {
  id: number;
  title: string | null;
  favicon_url: string | null;
  url_site: string | null;
}

export interface TopicMini {
  id: number;
  slug: string;
  display_name: string;
  type: string;
}

export interface ArticleListItem {
  id: number;
  url_canonical: string;
  title: string;
  description: string | null;
  image_url: string | null;
  image_local_url: string | null;
  image_width: number | null;
  image_height: number | null;
  author: string | null;
  published_at: string;
  source: ArticleSourceMini;
  topics: TopicMini[];
  category_color?: string | null;
}

export interface ArticleDetailOut extends ArticleListItem {
  content_html: string | null;
  content_text: string | null;
  internal_links: Array<{ url: string; text: string }>;
}

export type RelatedFormula = "coverage" | "source" | "max" | "jaccard";

export interface RelatedArticleItem extends ArticleListItem {
  overlap: number;
}

export interface RelatedArticlesOut {
  items: RelatedArticleItem[];
  formula: RelatedFormula;
  min_overlap: number;
  days_window: number;
}

export interface ArticleListOut {
  items: ArticleListItem[];
  next_cursor: string | null;
}

// ---- Search -----------------------------------------------------------------

export interface SearchHighlights {
  title: string;
  description: string;
  content_text: string;
}

export interface SearchResultItem extends ArticleListItem {
  highlights: SearchHighlights;
}

export interface SearchOut {
  items: SearchResultItem[];
  total: number;
  limit: number;
  offset: number;
  query: string;
}

export interface SuggestTopicItem {
  id: number;
  slug: string;
  display_name: string;
  type: string;
}

export interface SuggestSourceItem {
  id: number;
  title: string | null;
  url_site: string | null;
}

export interface SuggestOut {
  topics: SuggestTopicItem[];
  sources: SuggestSourceItem[];
}

export interface MessageOut {
  message: string;
}

export interface DeviceOut {
  id: string;
  client: string;
  ip: string | null;
  country: string | null;
  ua: string | null;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}

export interface NotificationOut {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  payload: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationCountOut {
  unread: number;
}

export interface AlertTopicOut {
  id: number;
  slug: string;
  display_name: string;
  type: string;
}

export type AlertMatchMode = "all" | "any";

export interface AlertOut {
  id: number;
  is_enabled: boolean;
  channels: string[];
  match_mode: AlertMatchMode;
  created_at: string;
  updated_at: string;
  topics: AlertTopicOut[];
}

export interface VapidKeyOut {
  public_key: string;
  configured: boolean;
}

export interface BookmarkOut {
  article: ArticleListItem;
  created_at: string;
}

export interface BookmarkIdsOut {
  ids: number[];
}

export interface PushSubscriptionOut {
  id: number;
  endpoint: string;
  ua: string | null;
  created_at: string;
  last_seen_at: string;
}

export interface ApiError {
  error: { code: string; message: string };
}

// ---- Sources / Categories ---------------------------------------------------

export interface SourceOut {
  id: number;
  kind: string;
  url_site: string | null;
  url_feed: string | null;
  wp_api_root: string | null;
  title: string | null;
  favicon_url: string | null;
  status: string;
}

export interface UserSourceOut {
  id: number;
  category_id: number;
  custom_title: string | null;
  added_at: string;
  source: SourceOut;
}

export interface UserSourceListOut {
  items: UserSourceOut[];
}

export interface FeaturedSourceItem {
  source_id: number;
  display_name: string | null;
  description: string | null;
  position: number;
  source: SourceOut;
}

export interface FeaturedSourcesOut {
  by_category: Record<string, FeaturedSourceItem[]>;
}

export interface FeedCandidatePreview {
  url_feed: string;
  title: string | null;
  sample_articles: Array<{ title: string; url: string; published_at: string }>;
}

export interface OgPreview {
  title: string | null;
  description: string | null;
  image: string | null;
  site_name: string | null;
  favicon: string | null;
}

export interface DiscoveryOut {
  kind: "rss" | "wordpress_api" | "invalid";
  source_id: number | null;
  url_site: string | null;
  url_feed: string | null;
  wp_api_root: string | null;
  candidates: FeedCandidatePreview[];
  og: OgPreview;
  reason: string | null;
}

export interface CategoryOut {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
  position: number;
  color: string | null;
  is_public: boolean;
}

export interface CategoryNode extends CategoryOut {
  children: CategoryNode[];
}

export interface CategoryTreeOut {
  tree: CategoryNode[];
}
