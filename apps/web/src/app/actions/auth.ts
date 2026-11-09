"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { authErrorMessage } from "@/lib/auth-errors";
import { claimsToSession, homeFor, safeNext } from "@/lib/auth-rules";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

export type FormState = {
  error?: string;
  /** Lỗi "email đã đăng ký": hiện kèm link Đăng nhập (US-01/AC3). */
  emailTaken?: boolean;
  message?: string;
};

const NOT_CONFIGURED: FormState = {
  error: "Chưa cấu hình Supabase (thiếu NEXT_PUBLIC_SUPABASE_URL / PUBLISHABLE_KEY).",
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Địa chỉ gốc của site hiện tại (production, preview hay localhost) để tạo link trong email. */
async function siteOrigin(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

function text(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

export async function signUpAction(_prev: FormState, formData: FormData): Promise<FormState> {
  if (!isSupabaseConfigured) return NOT_CONFIGURED;
  const email = text(formData, "email").toLowerCase();
  const password = formData.get("password")?.toString() ?? "";
  const confirm = formData.get("confirm")?.toString() ?? "";

  if (!EMAIL_RE.test(email)) return { error: "Địa chỉ email không hợp lệ." };
  if (password.length < 8) return { error: "Mật khẩu cần ít nhất 8 ký tự." };
  if (password !== confirm) return { error: "Hai lần nhập mật khẩu không khớp." };
  if (formData.get("agree") !== "on") return { error: "Bạn cần đồng ý Điều khoản để đăng ký." };

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${await siteOrigin()}/auth/callback` },
  });

  if (error) {
    const taken = error.code === "user_already_exists" || error.code === "email_exists";
    return { error: authErrorMessage(error), emailTaken: taken };
  }
  // Khi bật xác nhận email, Supabase không báo lỗi cho email đã tồn tại (chống dò email)
  // mà trả user không có identity nào.
  if (data.user && data.user.identities?.length === 0) {
    return { error: "Email này đã được đăng ký.", emailTaken: true };
  }
  if (data.session) {
    // Project tắt xác nhận email: đăng nhập luôn.
    redirect("/");
  }
  return {
    message: `Đã gửi email xác nhận tới ${email}. Mở hộp thư và bấm link để kích hoạt tài khoản.`,
  };
}

export async function signInAction(_prev: FormState, formData: FormData): Promise<FormState> {
  if (!isSupabaseConfigured) return NOT_CONFIGURED;
  const email = text(formData, "email").toLowerCase();
  const password = formData.get("password")?.toString() ?? "";
  if (!email || !password) return { error: "Nhập email và mật khẩu." };

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: authErrorMessage(error) };

  const { data } = await supabase.auth.getClaims();
  const session = claimsToSession(data?.claims as Record<string, unknown> | undefined);
  if (session?.status === "locked") {
    await supabase.auth.signOut({ scope: "local" });
    return { error: "Tài khoản đang bị khóa. Liên hệ quản trị viên." };
  }
  redirect(safeNext(text(formData, "next")) ?? homeFor(session?.role ?? "seeker"));
}

export async function googleSignInAction(formData: FormData): Promise<void> {
  if (!isSupabaseConfigured) redirect("/dang-nhap?loi=config");
  const supabase = await createClient();
  const callback = new URL("/auth/callback", await siteOrigin());
  const next = safeNext(text(formData, "next"));
  if (next) callback.searchParams.set("next", next);

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: callback.toString() },
  });
  if (error || !data.url) redirect("/dang-nhap?loi=google");
  redirect(data.url);
}

export async function forgotPasswordAction(_prev: FormState, formData: FormData): Promise<FormState> {
  if (!isSupabaseConfigured) return NOT_CONFIGURED;
  const email = text(formData, "email").toLowerCase();
  if (!EMAIL_RE.test(email)) return { error: "Địa chỉ email không hợp lệ." };

  const supabase = await createClient();
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${await siteOrigin()}/auth/callback?next=/dat-lai-mat-khau`,
  });
  if (error?.status === 429) return { error: authErrorMessage(error) };
  // Cùng một câu cho mọi trường hợp: không tiết lộ email có tồn tại hay không.
  return { message: "Nếu email tồn tại, chúng tôi đã gửi link đặt lại mật khẩu. Kiểm tra hộp thư." };
}

export async function resetPasswordAction(_prev: FormState, formData: FormData): Promise<FormState> {
  if (!isSupabaseConfigured) return NOT_CONFIGURED;
  const password = formData.get("password")?.toString() ?? "";
  const confirm = formData.get("confirm")?.toString() ?? "";
  if (password.length < 8) return { error: "Mật khẩu cần ít nhất 8 ký tự." };
  if (password !== confirm) return { error: "Hai lần nhập mật khẩu không khớp." };

  const supabase = await createClient();
  const { error } = await supabase.auth.updateUser({ password });
  if (error) return { error: authErrorMessage(error) };

  const { data } = await supabase.auth.getClaims();
  const session = claimsToSession(data?.claims as Record<string, unknown> | undefined);
  redirect(homeFor(session?.role ?? "seeker"));
}

export async function signOutAction(formData: FormData): Promise<void> {
  if (isSupabaseConfigured) {
    const allDevices = formData.get("all_devices") === "on";
    const supabase = await createClient();
    // RPC api.logout_user (schema.sql v2.0): ghi last_logout_at + audit_log, xóa mọi phiên nếu chọn.
    // Lỗi RPC (vd. DB chưa có hàm) không được chặn việc đăng xuất.
    await supabase.schema("api").rpc("logout_user", { p_all_devices: allDevices });
    await supabase.auth.signOut({ scope: allDevices ? "global" : "local" });
  }
  redirect("/");
}
