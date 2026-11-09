import { NextResponse, type NextRequest } from "next/server";
import { claimsToSession, homeFor, safeNext } from "@/lib/auth-rules";
import { createClient } from "@/lib/supabase/server";

/**
 * Đích quay về sau khi bấm link trong email (xác nhận đăng ký, đặt lại mật khẩu)
 * hoặc sau khi đăng nhập Google. Supabase gửi kèm ?code=… để đổi lấy phiên.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      const { data } = await supabase.auth.getClaims();
      const session = claimsToSession(data?.claims as Record<string, unknown> | undefined);
      return NextResponse.redirect(`${origin}${next ?? homeFor(session?.role ?? "seeker")}`);
    }
  }
  // Link hết hạn, đã dùng, hoặc mở trên trình duyệt khác với lúc đăng ký.
  return NextResponse.redirect(`${origin}/dang-nhap?loi=link`);
}
