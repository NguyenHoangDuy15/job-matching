// Biến NEXT_PUBLIC_* được nhúng vào bundle lúc build, nên phải có mặt khi chạy `next build`
// (file .env.local ở máy, hoặc biến môi trường build trên Cloudflare).
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

// Khóa publishable (sb_publishable_…) hoặc anon key cũ đều dùng được. Đây là khóa công khai,
// quyền thật do RLS trên Postgres quyết định. KHÔNG dùng service_role key ở web.
export const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

// Cho phép build và chạy giao diện khi chưa có project Supabase (CI, máy mới clone).
export const isSupabaseConfigured = SUPABASE_URL !== "" && SUPABASE_KEY !== "";
