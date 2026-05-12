import { api } from "@/services/api";

export interface TopicDetailOut {
  id: number;
  slug: string;
  display_name: string;
  type: string;
  description: string | null;
  wikipedia_url: string | null;
}

export async function fetchTopic(id: number): Promise<TopicDetailOut> {
  return api.get(`yf_topics/${id}`).json<TopicDetailOut>();
}
