import { api } from "@/services/api";
import type {
  NotificationCountOut,
  NotificationOut,
} from "@/types/api";

export async function listNotifications(opts?: {
  onlyUnread?: boolean;
  limit?: number;
  offset?: number;
}): Promise<NotificationOut[]> {
  const params = new URLSearchParams();
  if (opts?.onlyUnread) params.set("only_unread", "true");
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return api
    .get(`yf_me/notifications${qs ? `?${qs}` : ""}`)
    .json<NotificationOut[]>();
}

export async function unreadCount(): Promise<NotificationCountOut> {
  return api
    .get("yf_me/notifications/unread-count")
    .json<NotificationCountOut>();
}

export async function markRead(id: number): Promise<NotificationOut> {
  return api
    .patch(`yf_me/notifications/${id}/read`)
    .json<NotificationOut>();
}

export async function markAllRead(): Promise<NotificationCountOut> {
  return api
    .post("yf_me/notifications/mark-all-read")
    .json<NotificationCountOut>();
}

export async function deleteNotification(id: number): Promise<void> {
  await api.delete(`yf_me/notifications/${id}`);
}

export async function clearRead(): Promise<{ message: string }> {
  return api
    .post("yf_me/notifications/clear-read")
    .json<{ message: string }>();
}
