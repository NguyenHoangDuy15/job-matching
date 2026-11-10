import Link from "next/link";
import { PageShell, StatCard } from "@/components/home-cards";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getSession } from "@/lib/auth";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

/** Số tin IT đang mở (view api.v_open_jobs). null khi DB chưa sẵn sàng. */
async function countOpenJobs(): Promise<number | null> {
  if (!isSupabaseConfigured) return null;
  const supabase = await createClient();
  const { count, error } = await supabase
    .schema("api")
    .from("v_open_jobs")
    .select("id", { count: "exact", head: true });
  return error ? null : count;
}

function SearchBox() {
  // Trang /viec-lam (S2-H03) đọc ?q= để tìm kiếm.
  return (
    <form action="/viec-lam" className="flex gap-2">
      <Input
        name="q"
        aria-label="Từ khóa tìm việc"
        placeholder="Tìm việc: chức danh, kỹ năng, công ty… (gõ không dấu được)"
        className="h-10"
      />
      <button type="submit" className={cn(buttonVariants({ size: "lg" }), "h-10 px-5")}>
        Tìm
      </button>
    </form>
  );
}

export default async function HomePage() {
  const [session, openJobs] = await Promise.all([getSession(), countOpenJobs()]);
  const jobsValue = openJobs === null ? undefined : openJobs.toLocaleString("vi-VN");

  if (!session) {
    return (
      <PageShell title="Việc làm IT thật, ghép với CV của bạn có giải thích">
        <p className="max-w-2xl text-muted-foreground">
          Tin tuyển dụng IT được thu thập mỗi ngày từ nhiều trang tuyển dụng lớn. Tạo tài khoản để
          tải CV và nhận gợi ý việc phù hợp kèm lý do.
        </p>
        <SearchBox />
        <div className="flex gap-2">
          <Link href="/dang-ky" className={buttonVariants()}>
            Tạo tài khoản
          </Link>
          <Link href="/viec-lam" className={buttonVariants({ variant: "outline" })}>
            Xem việc làm
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard label="Việc IT đang mở" value={jobsValue} hint="Dữ liệu nối ở S2-H02" />
        </div>
      </PageShell>
    );
  }

  const name = session.email?.split("@")[0] ?? "bạn";
  return (
    <PageShell title={`Chào ${name}`}>
      <SearchBox />
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Việc IT đang mở" value={jobsValue} hint="Từ các nguồn đang bật" />
        <StatCard label="Việc mới 24 giờ" hint="Nối dữ liệu ở S2-H02" soon />
        <StatCard label="Tải CV để nhận Top N việc phù hợp" hint="Sprint 3–4" soon />
      </div>
    </PageShell>
  );
}
