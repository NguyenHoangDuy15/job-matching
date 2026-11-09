import type { Metadata } from "next";
import Link from "next/link";
import { AuthCard, GoogleButton, OrDivider } from "@/components/auth/auth-card";
import { SignInForm } from "@/components/auth/auth-forms";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { safeNext } from "@/lib/auth-rules";

export const metadata: Metadata = { title: "Đăng nhập" };

// Thông báo khi bị chuyển về trang này (?loi=…) từ proxy, callback hoặc nút Google.
const NOTICES: Record<string, string> = {
  locked: "Tài khoản đang bị khóa. Liên hệ quản trị viên.",
  link: "Link đã hết hạn, đã được dùng, hoặc được mở trên trình duyệt khác. Thử lại hoặc yêu cầu gửi email mới.",
  google: "Không đăng nhập được bằng Google. Thử lại sau.",
  config: "Chưa cấu hình Supabase cho môi trường này.",
};

export default async function SignInPage({ searchParams }: PageProps<"/dang-nhap">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null) ?? undefined;
  const notice = typeof params.loi === "string" ? NOTICES[params.loi] : undefined;

  return (
    <AuthCard
      title="Đăng nhập"
      footer={
        <>
          Chưa có tài khoản?{" "}
          <Link href="/dang-ky" className="underline underline-offset-4">
            Đăng ký
          </Link>
        </>
      }
    >
      {notice && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      <GoogleButton next={next} />
      <OrDivider text="hoặc" />
      <SignInForm next={next} />
    </AuthCard>
  );
}
