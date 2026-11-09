"use client";

import Link from "next/link";
import { useActionState } from "react";
import {
  type FormState,
  forgotPasswordAction,
  resetPasswordAction,
  signInAction,
  signUpAction,
} from "@/app/actions/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const initial: FormState = {};

function Field({ id, label, ...props }: { id: string; label: string } & React.ComponentProps<"input">) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={id} {...props} />
    </div>
  );
}

function FormMessages({ state }: { state: FormState }) {
  if (state.error) {
    return (
      <Alert variant="destructive" role="alert">
        <AlertDescription>
          {state.error}{" "}
          {state.emailTaken && (
            <Link href="/dang-nhap" className="font-medium underline">
              Đăng nhập
            </Link>
          )}
        </AlertDescription>
      </Alert>
    );
  }
  if (state.message) {
    return (
      <Alert role="status">
        <AlertDescription>{state.message}</AlertDescription>
      </Alert>
    );
  }
  return null;
}

export function SignUpForm() {
  const [state, action, pending] = useActionState(signUpAction, initial);
  return (
    <form action={action} className="grid gap-3">
      <Field id="email" label="Email" type="email" autoComplete="email" required />
      <Field
        id="password"
        label="Mật khẩu (ít nhất 8 ký tự)"
        type="password"
        autoComplete="new-password"
        minLength={8}
        required
      />
      <Field id="confirm" label="Nhập lại mật khẩu" type="password" autoComplete="new-password" required />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="agree" className="mt-0.5" required />
        <span>Tôi đồng ý Điều khoản sử dụng và Chính sách quyền riêng tư</span>
      </label>
      <Button type="submit" disabled={pending}>
        {pending ? "Đang tạo tài khoản…" : "Đăng ký"}
      </Button>
      <FormMessages state={state} />
    </form>
  );
}

export function SignInForm({ next }: { next?: string }) {
  const [state, action, pending] = useActionState(signInAction, initial);
  return (
    <form action={action} className="grid gap-3">
      <input type="hidden" name="next" value={next ?? ""} />
      <Field id="email" label="Email" type="email" autoComplete="email" required />
      <Field id="password" label="Mật khẩu" type="password" autoComplete="current-password" required />
      <div className="text-right text-sm">
        <Link href="/quen-mat-khau" className="underline underline-offset-4">
          Quên mật khẩu?
        </Link>
      </div>
      <Button type="submit" disabled={pending}>
        {pending ? "Đang đăng nhập…" : "Đăng nhập"}
      </Button>
      <FormMessages state={state} />
    </form>
  );
}

export function ForgotPasswordForm() {
  const [state, action, pending] = useActionState(forgotPasswordAction, initial);
  return (
    <form action={action} className="grid gap-3">
      <Field id="email" label="Email đã đăng ký" type="email" autoComplete="email" required />
      <Button type="submit" disabled={pending}>
        {pending ? "Đang gửi…" : "Gửi link đặt lại mật khẩu"}
      </Button>
      <FormMessages state={state} />
    </form>
  );
}

export function ResetPasswordForm() {
  const [state, action, pending] = useActionState(resetPasswordAction, initial);
  return (
    <form action={action} className="grid gap-3">
      <Field
        id="password"
        label="Mật khẩu mới (ít nhất 8 ký tự)"
        type="password"
        autoComplete="new-password"
        minLength={8}
        required
      />
      <Field id="confirm" label="Nhập lại mật khẩu mới" type="password" autoComplete="new-password" required />
      <Button type="submit" disabled={pending}>
        {pending ? "Đang lưu…" : "Lưu mật khẩu mới"}
      </Button>
      <FormMessages state={state} />
    </form>
  );
}
