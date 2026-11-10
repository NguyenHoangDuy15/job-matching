import { googleSignInAction } from "@/app/actions/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Khung chung cho các trang Đăng ký / Đăng nhập / Quên mật khẩu. */
export function AuthCard({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 items-start justify-center px-4 py-10">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent className="grid gap-4">
          {children}
          {footer && <div className="text-center text-sm text-muted-foreground">{footer}</div>}
        </CardContent>
      </Card>
    </div>
  );
}

export function GoogleButton({ next }: { next?: string }) {
  return (
    <form action={googleSignInAction}>
      <input type="hidden" name="next" value={next ?? ""} />
      <Button type="submit" variant="outline" className="w-full">
        Tiếp tục với Google
      </Button>
    </form>
  );
}

export function OrDivider({ text = "hoặc dùng email" }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <span className="h-px flex-1 bg-border" />
      {text}
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
