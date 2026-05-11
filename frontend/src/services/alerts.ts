import { api } from "@/services/api";
import type { AlertOut } from "@/types/api";

export async function listAlerts(): Promise<AlertOut[]> {
  return api.get("yf_me/alerts").json<AlertOut[]>();
}

export async function createAlert(topicId: number, channels?: string[]): Promise<AlertOut> {
  return api
    .post("yf_me/alerts", { json: { topic_id: topicId, channels } })
    .json<AlertOut>();
}

export async function updateAlert(
  alertId: number,
  patch: { is_enabled?: boolean; channels?: string[] },
): Promise<AlertOut> {
  return api
    .patch(`yf_me/alerts/${alertId}`, { json: patch })
    .json<AlertOut>();
}

export async function deleteAlert(alertId: number): Promise<void> {
  await api.delete(`yf_me/alerts/${alertId}`);
}
