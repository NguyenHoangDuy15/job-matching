import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AuthCard } from "@/components/auth/auth-card";
import { ResetPasswordForm } from "@/components/auth/auth-forms";
import { getSession } from "@/lib/auth";

export const metadata: Metadata = { title: "Đặt lại mật khẩu" };

// Người dùng tới đây từ link trong email (đã đổi code lấy phiên ở /auth/callback).
export default async function ResetPasswordPage() {
  const session = await getSession();
  if (!session) redirect("/dang-nhap?loi=link");

  return (
    <AuthCard title="Đặt mật khẩu mới" description={session.email ?? undefined}>
      <ResetPasswordForm />
    </AuthCard>
  );
}
