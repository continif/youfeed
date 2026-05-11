// Test degli schema Zod usati dai form auth: vincoli speculari al backend.

import { describe, it, expect } from "vitest";
import { loginSchema, registerSchema, resendVerificationSchema } from "@/schemas/auth";

describe("loginSchema", () => {
  it("accepts a valid login", () => {
    expect(loginSchema.safeParse({ identifier: "drtarr", password: "..pwd.." }).success).toBe(
      true,
    );
  });

  it("rejects identifier shorter than 3", () => {
    const r = loginSchema.safeParse({ identifier: "ab", password: "p" });
    expect(r.success).toBe(false);
    if (!r.success) {
      const msgs = r.error.issues.map((i) => i.message);
      expect(msgs.some((m) => m.includes("3"))).toBe(true);
    }
  });

  it("rejects empty password", () => {
    const r = loginSchema.safeParse({ identifier: "drtarr", password: "" });
    expect(r.success).toBe(false);
  });
});

describe("registerSchema", () => {
  it("accepts a valid registration", () => {
    expect(
      registerSchema.safeParse({
        username: "drtarr",
        email: "drtarr@drtarr.it",
        password: "..Y0uF33dT3st..",
      }).success,
    ).toBe(true);
  });

  it("rejects username < 3", () => {
    const r = registerSchema.safeParse({
      username: "dr",
      email: "x@y.it",
      password: "longenough10",
    });
    expect(r.success).toBe(false);
  });

  it("rejects username with invalid characters", () => {
    const r = registerSchema.safeParse({
      username: "dr.tarr",
      email: "x@y.it",
      password: "longenough10",
    });
    expect(r.success).toBe(false);
  });

  it("rejects malformed email", () => {
    const r = registerSchema.safeParse({
      username: "drtarr",
      email: "not-an-email",
      password: "longenough10",
    });
    expect(r.success).toBe(false);
  });

  it("rejects password < 10 chars (allineato al backend)", () => {
    const r = registerSchema.safeParse({
      username: "drtarr",
      email: "x@y.it",
      password: "short",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues.some((i) => i.path[0] === "password")).toBe(true);
    }
  });

  it("accepts username with underscore + digits", () => {
    expect(
      registerSchema.safeParse({
        username: "user_42",
        email: "x@y.it",
        password: "longenough10",
      }).success,
    ).toBe(true);
  });
});

describe("resendVerificationSchema", () => {
  it("accepts a valid email", () => {
    expect(resendVerificationSchema.safeParse({ email: "x@y.it" }).success).toBe(true);
  });

  it("rejects malformed email", () => {
    expect(resendVerificationSchema.safeParse({ email: "not-mail" }).success).toBe(false);
  });
});
