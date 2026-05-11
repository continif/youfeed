import { api } from "@/services/api";
import type { MessageOut, UserOut } from "@/types/api";

export async function getMe(): Promise<UserOut> {
  return api.get("yf_me").json<UserOut>();
}

export async function login(identifier: string, password: string): Promise<MessageOut> {
  return api
    .post("yf_auth/login", { json: { identifier, password } })
    .json<MessageOut>();
}

export async function register(
  username: string,
  email: string,
  password: string,
): Promise<MessageOut> {
  return api
    .post("yf_auth/register", { json: { username, email, password } })
    .json<MessageOut>();
}

export async function logout(): Promise<MessageOut> {
  return api.post("yf_auth/logout").json<MessageOut>();
}

export async function verifyEmail(token: string): Promise<MessageOut> {
  return api
    .get(`yf_auth/verify-email?token=${encodeURIComponent(token)}`)
    .json<MessageOut>();
}

export async function resendVerification(email: string): Promise<MessageOut> {
  return api
    .post("yf_auth/resend-verification", { json: { email } })
    .json<MessageOut>();
}

export async function forgotPassword(email: string): Promise<MessageOut> {
  return api.post("yf_auth/forgot-password", { json: { email } }).json<MessageOut>();
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<MessageOut> {
  return api
    .post("yf_auth/reset-password", { json: { token, new_password: newPassword } })
    .json<MessageOut>();
}
