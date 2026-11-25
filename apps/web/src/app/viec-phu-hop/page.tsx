import { UploadCloud } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/home-cards";
import { MatchFilters, type CvOption } from "@/components/match/match-filters";
import { MatchResults } from "@/components/match/match-results";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { requireAccess } from "@/lib/auth";
import { cvLabel } from "@/lib/cv-list";
import { matchableCvs, matchHref, parseMatchParams, pickCv, toMatchRequest } from "@/lib/match";
import { parseSimulation } from "@/lib/match-errors";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Việc phù hợp với tôi" };

// S4-H01 · US-16 · docs/ui/wireframe_matches.png (màn 1). Chỉ người tìm việc (proxy chặn vai trò khác).
// Danh sách CV: api.v_my_cvs (RLS chỉ trả CV của mình). Kết quả: lib/match-source.ts (mock, S4-H04 nối API).
// Lựa chọn nằm trên URL: /viec-phu-hop?cv=<uuid>&n=10&tinh=1,79&hinh-thuc=remote

const TITLE = "Việc phù hợp với tôi";

type CvRow = {
  id: string;
  mime: string;
  original_name: string | null;
  parse_status: string;
  is_primary: boolean;
  created_at: string;
  profile_confirmed_at: string | null;
};

export default async function MatchPage({ searchParams }: PageProps<"/viec-phu-hop">) {
  await requireAccess("/viec-phu-hop");
  const query = await searchParams;
  const params = parseMatchParams(query);
  const simulate = parseSimulation(query["gia-lap"]); // S4-H03: giả lập lỗi khi đang dùng dữ liệu mẫu

  const api = (await createClient()).schema("api");
  const cvs = await api
    .from("v_my_cvs")
    .select("id, mime, original_name, parse_status, is_primary, created_at, profile_confirmed_at")
    .returns<CvRow[]>();

  if (cvs.error) {
    return (
      <PageShell title={TITLE}>
        <Alert variant="destructive" className="max-w-3xl">
          <AlertTitle>Chưa đọc được danh sách CV</AlertTitle>
          <AlertDescription>Hãy tải lại trang sau ít phút.</AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  const all = cvs.data ?? [];
  const matchable = matchableCvs(all);
  const cv = pickCv(matchable, params.cvId);

  if (!cv) {
    const reading = all.some((c) => c.parse_status === "queued" || c.parse_status === "parsing");
    return (
      <PageShell title={TITLE}>
        <div className="grid max-w-3xl justify-items-center gap-3 rounded-lg border-2 border-dashed p-10 text-center">
          <UploadCloud className="size-8 text-muted-foreground" aria-hidden />
          <p className="font-medium">
            {reading ? "CV của bạn đang được đọc" : "Bạn cần tải CV để nhận việc phù hợp"}
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            {reading
              ? "Hãy đợi hệ thống đọc xong CV rồi quay lại trang này."
              : "Hệ thống đọc kỹ năng trong CV rồi chấm điểm các tin đang mở để gợi ý việc hợp với bạn."}
          </p>
          <Link href={all.length ? "/ho-so" : "/ho-so/tai-cv"} className={buttonVariants()}>
            {all.length ? "Về Hồ sơ CV" : "Tải CV"}
          </Link>
        </div>
      </PageShell>
    );
  }

  const selected = { ...params, cvId: cv.id };
  const href = matchHref(selected);
  const options: CvOption[] = matchable.map((c) => ({
    id: c.id,
    label: cvLabel(c),
    isPrimary: c.is_primary,
    confirmed: c.profile_confirmed_at != null,
  }));

  return (
    <PageShell title={TITLE}>
      <MatchFilters key={`f-${href}`} params={selected} cvs={options} />
      {!cv.profile_confirmed_at && (
        <p className="text-sm text-muted-foreground">
          CV này chưa được xác nhận hồ sơ kỹ năng.{" "}
          <Link href={`/ho-so/${cv.id}/xac-nhan`} className="text-primary underline-offset-2 hover:underline">
            Xác nhận hồ sơ
          </Link>{" "}
          để điểm sát hơn.
        </p>
      )}
      <MatchResults
        key={`r-${href}-${simulate ?? ""}`}
        request={toMatchRequest(selected, cv.id)}
        simulate={simulate}
      />
    </PageShell>
  );
}
