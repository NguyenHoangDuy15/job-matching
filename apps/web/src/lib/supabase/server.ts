import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { SUPABASE_KEY, SUPABASE_URL } from "./env";

/**
 * Client Supabase cho Server Component, Server Action và Route Handler.
 * Tạo mới cho từng request, không dùng chung giữa các request.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(SUPABASE_URL, SUPABASE_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options),
          );
        } catch {
          // Server Component không được ghi cookie. Không sao: proxy.ts đã làm mới phiên
          // ở mỗi request trước khi trang render.
        }
      },
    },
  });
}
