import type { Metadata } from "next";
import Link from "next/link";
import { AuthCard } from "@/components/auth/auth-card";
import { ForgotPasswordForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = { title: "Quên mật khẩu" };

export default function ForgotPasswordPage() {
  return (
    <AuthCard
      title="Quên mật khẩu"
      description="Nhập email đã đăng ký, chúng tôi gửi link để đặt mật khẩu mới."
      footer={
        <Link href="/dang-nhap" className="underline underline-offset-4">
          Quay lại đăng nhập
        </Link>
      }
    >
      <ForgotPasswordForm />
    </AuthCard>
  );
}
