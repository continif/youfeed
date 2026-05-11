import { api } from "@/services/api";
import type { DeviceOut, MessageOut, UserOut } from "@/types/api";

export async function patchMe(patch: { onboarding_completed?: boolean }): Promise<UserOut> {
  return api.patch("yf_me", { json: patch }).json<UserOut>();
}

export async function completeOnboarding(): Promise<UserOut> {
  return patchMe({ onboarding_completed: true });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<MessageOut> {
  return api
    .post("yf_me/change-password", {
      json: { current_password: currentPassword, new_password: newPassword },
    })
    .json<MessageOut>();
}

/**
 * GDPR Art. 20: scarica un ZIP con i dati utente.
 * Triggera il download direttamente dal browser tramite un blob URL.
 */
export async function downloadExport(filename = "youfeed-export.zip"): Promise<void> {
  const blob = await api.get("yf_me/export").blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function deleteAccount(): Promise<void> {
  await api.delete("yf_me");
}

export async function listDevices(): Promise<DeviceOut[]> {
  return api.get("yf_me/devices").json<DeviceOut[]>();
}

export async function revokeDevice(id: string): Promise<MessageOut> {
  return api.delete(`yf_me/devices/${encodeURIComponent(id)}`).json<MessageOut>();
}
