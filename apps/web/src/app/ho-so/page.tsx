import { UploadCloud } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { CvList } from "@/components/cv/cv-list";
import { PageShell } from "@/components/home-cards";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { requireAccess } from "@/lib/auth";
import { countSkills, sortCvs, type CvListRow } from "@/lib/cv-list";
import { MAX_CVS } from "@/lib/cv-file";
import type { EvidenceLevel } from "@/lib/cv-profile";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Hồ sơ của tôi" };

// S3-H04 · US-13 · docs/ui/wireframe_cv.png (màn 4). Chỉ người tìm việc (proxy chặn vai trò khác).
// api.v_my_cvs (0015: is_primary, delete_after) + api.v_my_cv_skills (0010) để đếm kỹ năng.
// RLS chỉ trả CV của chính mình.

const CV_COLUMNS =
  "id, mime, parse_status, parse_error, is_primary, created_at, original_name, years_exp, target_title, profile_confirmed_at, delete_after";

export default async function MyProfilePage() {
  await requireAccess("/ho-so");

  const api = (await createClient()).schema("api");
  const [cvs, skills] = await Promise.all([
    api.from("v_my_cvs").select(CV_COLUMNS).returns<CvListRow[]>(),
    api.from("v_my_cv_skills").select("cv_id, evidence_level").returns<{ cv_id: string; evidence_level: EvidenceLevel }[]>(),
  ]);

  if (cvs.error || skills.error) {
    const missing = cvs.error?.code === "42703" || cvs.error?.code === "PGRST204";
    return (
      <PageShell title="Hồ sơ của tôi">
        <Alert variant="destructive" className="max-w-3xl">
          <AlertTitle>Chưa đọc được danh sách CV</AlertTitle>
          <AlertDescription>
            {missing
              ? "Database chưa có migration 0015 (CV chính, hạn lưu). Báo nhóm chạy migration rồi tải lại trang."
              : "Hãy tải lại trang sau ít phút."}
          </AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  const rows = sortCvs(cvs.data ?? []);
  const counts = Object.fromEntries(countSkills(skills.data ?? []));
  const full = rows.length >= MAX_CVS;

  return (
    <PageShell title="Hồ sơ của tôi">
      <div className="grid max-w-5xl gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-muted-foreground">
            Bạn đang có{" "}
            <b className="text-foreground">
              {rows.length}/{MAX_CVS}
            </b>{" "}
            CV
          </p>
          {rows.length > 0 &&
            (full ? (
              <span className="ml-auto text-xs text-muted-foreground">Đã đủ {MAX_CVS} CV: xóa bớt để tải CV mới.</span>
            ) : (
              <Link href="/ho-so/tai-cv" className={buttonVariants({ className: "ml-auto" })}>
                + Tải CV mới
              </Link>
            ))}
        </div>

        {rows.length === 0 ? (
          <div className="grid justify-items-center gap-3 rounded-lg border-2 border-dashed p-10 text-center">
            <UploadCloud className="size-8 text-muted-foreground" aria-hidden />
            <p className="font-medium">Bạn chưa tải CV nào</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Tải CV (PDF hoặc DOCX) để hệ thống đọc kỹ năng và gợi ý việc làm phù hợp.
            </p>
            <Link href="/ho-so/tai-cv" className={buttonVariants()}>
              Tải CV
            </Link>
          </div>
        ) : (
          <CvList rows={rows} counts={counts} />
        )}
      </div>
    </PageShell>
  );
}
