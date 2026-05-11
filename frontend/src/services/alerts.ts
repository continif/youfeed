import { api } from "@/services/api";
import type { AlertOut, AlertMatchMode } from "@/types/api";

export async function listAlerts(): Promise<AlertOut[]> {
  return api.get("yf_me/alerts").json<AlertOut[]>();
}

export async function createAlert(
  topicIds: number[],
  opts: { channels?: string[]; matchMode?: AlertMatchMode } = {},
): Promise<AlertOut> {
  return api
    .post("yf_me/alerts", {
      json: {
        topic_ids: topicIds,
        channels: opts.channels,
        match_mode: opts.matchMode ?? "all",
      },
    })
    .json<AlertOut>();
}

export async function updateAlert(
  alertId: number,
  patch: {
    is_enabled?: boolean;
    channels?: string[];
    topic_ids?: number[];
    match_mode?: AlertMatchMode;
  },
): Promise<AlertOut> {
  return api
    .patch(`yf_me/alerts/${alertId}`, { json: patch })
    .json<AlertOut>();
}

export async function deleteAlert(alertId: number): Promise<void> {
  await api.delete(`yf_me/alerts/${alertId}`);
}
