import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import "./globals.css";

// Inter có bộ ký tự tiếng Việt (subset "vietnamese"); Geist mặc định thì không.
const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin", "vietnamese"],
});

export const metadata: Metadata = {
  title: { default: "JobMatch – Việc làm IT có giải thích", template: "%s · JobMatch" },
  description: "Tìm việc IT thật từ nhiều trang tuyển dụng, ghép CV với JD có giải thích.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className={`${inter.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        {!isSupabaseConfigured && (
          <div className="mx-auto w-full max-w-6xl px-4 pt-3">
            <Alert>
              <AlertDescription>
                Chưa cấu hình Supabase: đăng ký/đăng nhập chưa hoạt động. Tạo file
                <code className="mx-1">apps/web/.env.local</code> theo <code>.env.example</code>.
              </AlertDescription>
            </Alert>
          </div>
        )}
        <main className="flex flex-1 flex-col">{children}</main>
      </body>
    </html>
  );
}
