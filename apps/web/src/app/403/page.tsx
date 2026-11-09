import type { Metadata } from "next";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { getSession } from "@/lib/auth";
import { homeFor } from "@/lib/auth-rules";

export const metadata: Metadata = { title: "Không có quyền truy cập" };

// proxy.ts rewrite tới đây với mã 403 khi vai trò không được vào trang (US-02/AC2).
export default async function ForbiddenPage() {
  const session = await getSession();
  const home = session ? homeFor(session.role) : "/";

  return (
    <div className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-3 px-4 py-16 text-center">
      <p className="text-5xl font-bold">403</p>
      <h1 className="text-xl font-semibold">Bạn không có quyền truy cập</h1>
      <p className="text-muted-foreground">
        Trang này dành cho vai trò khác. Không có dữ liệu nào của trang được tải.
      </p>
      <Link href={home} className={buttonVariants()}>
        Về trang chủ của tôi
      </Link>
    </div>
  );
}
