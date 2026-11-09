import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import {
  GUEST_ONLY_PATHS,
  allowedRolesFor,
  canAccess,
  claimsToSession,
  homeFor,
} from "@/lib/auth-rules";
import { SUPABASE_KEY, SUPABASE_URL, isSupabaseConfigured } from "@/lib/supabase/env";

/**
 * Lớp phân quyền 1 (US-02): chạy trước khi trang render.
 *
 * Vì sao dùng middleware.ts (Next 16 báo deprecated) thay vì proxy.ts:
 * proxy.ts luôn chạy Node.js runtime, mà OpenNext Cloudflare chưa hỗ trợ chính thức Node middleware
 * (build báo "experimental … use at your own risk"). middleware.ts vẫn chạy Edge runtime,
 * được OpenNext hỗ trợ. Chuyển sang proxy.ts khi OpenNext hỗ trợ Node middleware
 * (https://opennext.js.org/cloudflare, mục "Supported Next.js features").
 * - Làm mới phiên Supabase và ghi lại cookie.
 * - Chặn khách vào trang cần đăng nhập, chặn sai vai trò bằng trang 403.
 * Lớp 2 là RLS + app.is_active_user() trong Postgres; mỗi trang cũng tự kiểm lại (lib/auth.ts).
 */
export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  if (!isSupabaseConfigured) return response;

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_KEY, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
        // Header chống CDN cache response có cookie phiên (tránh lộ phiên giữa người dùng).
        Object.entries(headers ?? {}).forEach(([key, value]) => response.headers.set(key, value));
      },
    },
  });

  // Không chèn code giữa createServerClient và getClaims: getClaims làm mới phiên nếu cần.
  const { data } = await supabase.auth.getClaims();
  const session = claimsToSession(data?.claims as Record<string, unknown> | undefined);
  const { pathname, search } = request.nextUrl;

  // Giữ cookie vừa làm mới khi trả về redirect/rewrite.
  const withCookies = (res: NextResponse) => {
    response.cookies.getAll().forEach((cookie) => res.cookies.set(cookie));
    return res;
  };

  if (session?.status === "locked") {
    await supabase.auth.signOut({ scope: "local" });
    if (pathname !== "/dang-nhap") {
      return withCookies(NextResponse.redirect(new URL("/dang-nhap?loi=locked", request.url)));
    }
    return response;
  }

  if (session && GUEST_ONLY_PATHS.includes(pathname)) {
    return withCookies(NextResponse.redirect(new URL(homeFor(session.role), request.url)));
  }

  if (allowedRolesFor(pathname)) {
    if (!session) {
      const login = new URL("/dang-nhap", request.url);
      login.searchParams.set("next", pathname + search);
      return withCookies(NextResponse.redirect(login));
    }
    if (!canAccess(session, pathname)) {
      // Rewrite (không redirect) để URL giữ nguyên, trả mã 403 và không tải dữ liệu trang gốc.
      return withCookies(NextResponse.rewrite(new URL("/403", request.url), { status: 403 }));
    }
  }

  return response;
}

export const config = {
  matcher: [
    // Bỏ qua file tĩnh và ảnh để không chạy kiểm phiên cho từng file.
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
