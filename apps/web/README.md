# apps/web — giao diện JobMatch (Next.js)

S2-H01 · Next.js 16 (App Router) + TypeScript + Tailwind 4 + shadcn/ui · Supabase Auth · deploy Cloudflare Workers qua OpenNext.

## Chạy ở máy

```bash
cd apps/web
npm install
cp .env.example .env.local   # điền URL và publishable key của project Supabase
npm run dev                   # http://localhost:3000
```

Thiếu `.env.local` vẫn chạy được giao diện; trang hiện thông báo "Chưa cấu hình Supabase" và đăng nhập không hoạt động.

| Lệnh | Việc |
|---|---|
| `npm run dev` | Chạy dev server Next.js |
| `npm run lint` · `npm run typecheck` | ESLint · kiểm kiểu (CI chạy cả hai) |
| `npm run preview` | Build OpenNext rồi chạy trên runtime Cloudflare (workerd) ở http://localhost:8787 |
| `npm run deploy` | Build và deploy lên Cloudflare (cần `npx wrangler login` trước) |

## Cấu trúc

```
src/
  middleware.ts          lớp phân quyền 1: làm mới phiên, chặn khách, sai vai trò → 403
  app/
    dang-ky, dang-nhap, quen-mat-khau, dat-lai-mat-khau    trang xác thực (US-01)
    auth/callback/route.ts   đổi ?code= lấy phiên (link email, Google)
    page.tsx · hr/ · admin/ · 403/     trang chủ theo vai trò (US-02)
    viec-lam/            tìm việc + bộ lọc trên URL, 20 tin/trang, skeleton (US-03, US-05)
    viec-lam/[id]/       chi tiết tin: kỹ năng, mô tả/yêu cầu/quyền lợi (US-06, api.v_job_detail)
    actions/auth.ts      Server Action: đăng ký, đăng nhập, Google, quên/đặt lại mật khẩu, đăng xuất
  components/jobs/       ô tìm kiếm, cột bộ lọc, thẻ việc, phân trang
  lib/
    jobs/                đọc/ghi bộ lọc URL, gọi rpc api.search_jobs, định dạng lương/ngày/nguồn
    auth-rules.ts        bảng route × vai trò, đọc claim JWT (user_role, account_status, org_id)
    auth.ts              getSession(), requireAccess() — kiểm quyền lần 2 trong trang
    supabase/            client trình duyệt / server, biến môi trường
```

Vai trò lấy từ claim mà `custom_access_token_hook` (schema.sql v2.0) nhúng vào JWT, đọc bằng `supabase.auth.getClaims()` (có xác thực chữ ký), không đọc từ cookie thô. Bảng route × vai trò: [`docs/ui/wireframe_auth.png`](../../docs/ui/wireframe_auth.png).

**Vì sao `middleware.ts` chứ không phải `proxy.ts`:** Next 16 đổi tên middleware thành proxy, nhưng proxy luôn chạy Node.js runtime, còn OpenNext Cloudflare chưa hỗ trợ chính thức Node middleware. `middleware.ts` vẫn chạy Edge runtime nên deploy ổn định. Next sẽ in cảnh báo deprecated khi build: đây là chủ ý.

## Deploy lên Cloudflare (lần đầu)

1. Tạo tài khoản Cloudflare, rồi ở máy: `npx wrangler login`.
2. Build cần biến `NEXT_PUBLIC_*` (được nhúng lúc build): có `.env.local` ở máy, hoặc khai báo trong Cloudflare.
3. `npm run deploy` → URL `https://jobmatch-web.<tài-khoản>.workers.dev`.
4. Supabase Dashboard → Authentication → URL Configuration: thêm URL production và `http://localhost:3000` vào **Site URL / Redirect URLs** (dạng `https://…/auth/callback`).

Preview cho mỗi PR: Cloudflare Dashboard → Workers → `jobmatch-web` → Settings → Builds → kết nối repo GitHub, thư mục gốc `apps/web`, lệnh build `npx opennextjs-cloudflare build`, lệnh deploy `npx opennextjs-cloudflare deploy`, bật preview cho nhánh khác `main`.
