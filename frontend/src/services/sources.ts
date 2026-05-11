import { api } from "@/services/api";
import type {
  DiscoveryOut,
  FeaturedSourcesOut,
  UserSourceListOut,
  UserSourceOut,
} from "@/types/api";

export async function listMySources(): Promise<UserSourceListOut> {
  return api.get("yf_me/sources").json<UserSourceListOut>();
}

export async function linkSource(
  sourceId: number,
  categoryId: number,
  customTitle?: string,
): Promise<UserSourceOut> {
  return api
    .post("yf_me/sources", {
      json: {
        source_id: sourceId,
        category_id: categoryId,
        custom_title: customTitle ?? null,
      },
    })
    .json<UserSourceOut>();
}

export async function updateMySource(
  userSourceId: number,
  patch: { category_id?: number; custom_title?: string | null },
): Promise<UserSourceOut> {
  return api
    .patch(`yf_me/sources/${userSourceId}`, { json: patch })
    .json<UserSourceOut>();
}

export async function unlinkSource(userSourceId: number): Promise<void> {
  await api.delete(`yf_me/sources/${userSourceId}`);
}

export async function fetchFeatured(): Promise<FeaturedSourcesOut> {
  return api.get("yf_sources/featured").json<FeaturedSourcesOut>();
}

export async function discoverUrl(url: string): Promise<DiscoveryOut> {
  return api.post("yf_sources/discover", { json: { url } }).json<DiscoveryOut>();
}
