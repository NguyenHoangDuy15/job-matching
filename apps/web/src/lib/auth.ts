import { redirect } from "next/navigation";
import { connection } from "next/server";
import { canAccess, claimsToSession, type SessionInfo } from "./auth-rules";
import { isSupabaseConfigured } from "./supabase/env";
import { createClient } from "./supabase/server";

/**
 * Phiên đăng nhập hiện tại, đọc từ JWT đã được Supabase xác thực (getClaims),
 * không tin cookie thô. null = khách hoặc chưa cấu hình Supabase.
 */
export async function getSession(): Promise<SessionInfo | null> {
  // Phiên khác nhau theo từng request: không bao giờ prerender lúc build,
  // kể cả khi build thiếu biến môi trường Supabase (CI).
  await connection();
  if (!isSupabaseConfigured) return null;
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data) return null;
  return claimsToSession(data.claims as Record<string, unknown>);
}

/**
 * Kiểm quyền lần 2 ngay trong trang (proxy là lớp 1). Không đủ quyền thì
 * chuyển về đăng nhập hoặc trang 403.
 */
export async function requireAccess(pathname: string): Promise<SessionInfo> {
  const session = await getSession();
  if (!session) redirect(`/dang-nhap?next=${encodeURIComponent(pathname)}`);
  if (session.status === "locked") redirect("/dang-nhap?loi=locked");
  if (!canAccess(session, pathname)) redirect("/403");
  return session;
}
