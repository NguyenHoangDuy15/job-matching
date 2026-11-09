import type { Metadata } from "next";
import { PageShell, StatCard } from "@/components/home-cards";
import { requireAccess } from "@/lib/auth";

export const metadata: Metadata = { title: "Quản trị" };

export default async function AdminHomePage() {
  await requireAccess("/admin");

  return (
    <PageShell title="Sức khỏe hệ thống">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Tin đang mở theo nguồn" hint="Sprint 4 (US-18)" soon />
        <StatCard label="Lần thu thập gần nhất" hint="Sprint 4 (US-18)" soon />
        <StatCard label="Người dùng theo vai trò" hint="Sprint 4 (US-18)" soon />
      </div>
      <p className="text-sm text-muted-foreground">
        Quản trị viên không đọc được CV của người dùng (đặc quyền tối thiểu). Mọi thao tác quản trị được
        ghi vào nhật ký.
      </p>
    </PageShell>
  );
}
