import type { Metadata } from "next";
import { PageShell, StatCard } from "@/components/home-cards";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { requireAccess } from "@/lib/auth";

export const metadata: Metadata = { title: "Nhà tuyển dụng" };

export default async function HrHomePage() {
  // Proxy đã chặn; kiểm lại ở đây phòng khi matcher của proxy bị đổi.
  const session = await requireAccess("/hr");

  if (session.status === "pending_hr") {
    return (
      <PageShell title="Tài khoản nhà tuyển dụng">
        <Alert>
          <AlertTitle>Yêu cầu đang chờ duyệt</AlertTitle>
          <AlertDescription>
            Yêu cầu tài khoản nhà tuyển dụng của bạn đang chờ quản trị viên duyệt. Khi được duyệt, các
            chức năng đăng JD và xếp hạng ứng viên sẽ mở.
          </AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  return (
    <PageShell title="Tổng quan tuyển dụng">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="JD đang tuyển" hint="Đăng JD (Sprint 5)" soon />
        <StatCard label="CV ứng viên đã tải" hint="Tải lô CV (Sprint 6)" soon />
        <StatCard label="Shortlist" hint="Sprint 6" soon />
      </div>
      <p className="text-sm text-muted-foreground">
        Bạn chỉ thấy dữ liệu của công ty mình. HR công ty khác không xem được JD hay CV của bạn.
      </p>
    </PageShell>
  );
}
