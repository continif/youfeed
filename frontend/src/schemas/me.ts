import { z } from "zod";

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Inserisci la password attuale"),
    new_password: z
      .string()
      .min(10, "La nuova password deve avere almeno 10 caratteri"),
    confirm_password: z.string(),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Le password non coincidono",
    path: ["confirm_password"],
  });

export type ChangePasswordInput = z.infer<typeof changePasswordSchema>;
