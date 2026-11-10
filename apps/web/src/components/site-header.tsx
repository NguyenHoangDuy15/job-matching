import Link from "next/link";
import { signOutAction } from "@/app/actions/auth";
import { Button, buttonVariants } from "@/components/ui/button";
import { getSession } from "@/lib/auth";
import { ROLE_LABEL, type Role, type SessionInfo } from "@/lib/auth-rules";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; soon?: string };

// Menu theo vai trò (US-02). Mục có `soon` là chức năng sprint sau: hiện mờ, chưa bấm được.
const NAV: Record<Role | "guest", NavItem[]> = {
  guest: [{ href: "/viec-lam", label: "Việc làm" }],
  seeker: [
    { href: "/", label: "Trang chủ" },
    { href: "/viec-lam", label: "Việc làm" },
    { href: "/viec-phu-hop", label: "Việc phù hợp", soon: "Sprint 4" },
    { href: "/ho-so", label: "Hồ sơ CV", soon: "Sprint 3" },
    { href: "/ky-nang-hot", label: "Kỹ năng hot", soon: "Sprint 6" },
  ],
  hr: [
    { href: "/hr", label: "Tổng quan" },
    { href: "/hr/jd", label: "JD của tôi", soon: "Sprint 5" },
    { href: "/hr/ung-vien", label: "Ứng viên", soon: "Sprint 6" },
  ],
  admin: [
    { href: "/admin", label: "Tổng quan" },
    { href: "/admin/nguoi-dung", label: "Người dùng", soon: "Sprint 7" },
    { href: "/admin/nguon", label: "Nguồn thu thập", soon: "Sprint 7" },
  ],
};

function navFor(session: SessionInfo | null): NavItem[] {
  if (!session) return NAV.guest;
  // Chờ duyệt HR: vẫn là người tìm việc, thêm lối vào trang /hr để xem trạng thái.
  if (session.status === "pending_hr" && session.role === "seeker") {
    return [...NAV.seeker, { href: "/hr", label: "Nhà tuyển dụng" }];
  }
  return NAV[session.role];
}

export async function SiteHeader() {
  const session = await getSession();

  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link href="/" className="font-bold">
          JobMatch
          {session && session.role !== "seeker" && (
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              {session.role === "hr" ? "HR" : "Admin"}
            </span>
          )}
        </Link>
        <nav aria-label="Menu chính" className="flex flex-wrap items-center gap-4 text-sm">
          {navFor(session).map((item) =>
            item.soon ? (
              <span key={item.href} className="text-muted-foreground/60" title={`Sắp có (${item.soon})`}>
                {item.label}
              </span>
            ) : (
              <Link key={item.href} href={item.href} className="hover:underline">
                {item.label}
              </Link>
            ),
          )}
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          {session ? (
            <>
              <span className="hidden text-muted-foreground sm:inline">
                {session.email} · {ROLE_LABEL[session.role]}
              </span>
              <form action={signOutAction} className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-muted-foreground">
                  <input type="checkbox" name="all_devices" />
                  mọi thiết bị
                </label>
                <Button type="submit" variant="outline" size="sm">
                  Đăng xuất
                </Button>
              </form>
            </>
          ) : (
            <>
              <Link href="/dang-nhap" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
                Đăng nhập
              </Link>
              <Link href="/dang-ky" className={cn(buttonVariants({ size: "sm" }))}>
                Đăng ký
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
