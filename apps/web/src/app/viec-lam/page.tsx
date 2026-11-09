import type { Metadata } from "next";
import { PageShell } from "@/components/home-cards";

export const metadata: Metadata = { title: "Việc làm" };

// Khung tạm để menu không dẫn tới 404. Danh sách, tìm kiếm và bộ lọc làm ở S2-H02, S2-H03
// theo docs/ui/wireframe_jobs.png.
export default async function JobsPage({ searchParams }: PageProps<"/viec-lam">) {
  const { q } = await searchParams;
  return (
    <PageShell title="Việc làm IT đang tuyển">
      {typeof q === "string" && q !== "" && (
        <p className="text-sm">
          Từ khóa: <b>{q}</b>
        </p>
      )}
      <p className="text-muted-foreground">
        Danh sách việc làm, tìm kiếm không dấu và bộ lọc sẽ có ở bản cập nhật tiếp theo (S2-H03).
      </p>
    </PageShell>
  );
}
