import type { Metadata } from "next";
import Link from "next/link";
import { AuthCard, GoogleButton, OrDivider } from "@/components/auth/auth-card";
import { SignUpForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = { title: "Đăng ký" };

export default function SignUpPage() {
  return (
    <AuthCard
      title="Tạo tài khoản người tìm việc"
      description="Lưu CV và nhận gợi ý việc làm phù hợp."
      footer={
        <>
          Đã có tài khoản?{" "}
          <Link href="/dang-nhap" className="underline underline-offset-4">
            Đăng nhập
          </Link>
          <br />
          Bạn là nhà tuyển dụng? Đăng ký tài khoản HR sẽ mở ở Sprint 5 (cần admin duyệt).
        </>
      }
    >
      <GoogleButton />
      <OrDivider />
      <SignUpForm />
    </AuthCard>
  );
}
