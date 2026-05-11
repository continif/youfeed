// Zod schemas riusabili per i form auth.
// Speculari ai vincoli in `backend/app/schemas/auth.py`.

import { z } from "zod";

export const loginSchema = z.object({
  identifier: z
    .string()
    .min(3, "Inserisci almeno 3 caratteri")
    .max(200, "Massimo 200 caratteri"),
  password: z.string().min(1, "La password è obbligatoria"),
});

export type LoginInput = z.infer<typeof loginSchema>;

// Backend: username 3-30, email valida, password >= 10
export const registerSchema = z.object({
  username: z
    .string()
    .min(3, "Lo username deve essere lungo almeno 3 caratteri")
    .max(30, "Massimo 30 caratteri")
    .regex(
      /^[a-zA-Z0-9_]+$/,
      "Solo lettere, numeri e underscore",
    ),
  email: z.string().email("Email non valida"),
  password: z
    .string()
    .min(10, "La password deve avere almeno 10 caratteri")
    .max(200, "Password troppo lunga"),
});

export type RegisterInput = z.infer<typeof registerSchema>;

export const resendVerificationSchema = z.object({
  email: z.string().email("Email non valida"),
});

export type ResendVerificationInput = z.infer<typeof resendVerificationSchema>;

export const forgotPasswordSchema = z.object({
  email: z.string().email("Email non valida"),
});

export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({
    new_password: z
      .string()
      .min(10, "La password deve avere almeno 10 caratteri")
      .max(200, "Password troppo lunga"),
    confirm_password: z.string().min(1, "Conferma la password"),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "Le password non coincidono",
    path: ["confirm_password"],
  });

export type ResetPasswordInput = z.infer<typeof resetPasswordSchema>;
