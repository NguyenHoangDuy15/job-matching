import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CvOriginal } from "@/components/cv/cv-original";
import { ParsePending } from "@/components/cv/parse-pending";
import { SkillConfirmForm } from "@/components/cv/skill-confirm-form";
import { PageShell } from "@/components/home-cards";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { requireAccess } from "@/lib/auth";
import { cvExtension, isUuid } from "@/lib/cv";
import type { CvSkill, EvidenceLevel, TaxonomySkill } from "@/lib/cv-profile";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Xác nhận hồ sơ CV" };

// S3-H02, S3-H03 · US-12 · docs/ui/wireframe_cv.png (màn 3). Chỉ người tìm việc (proxy chặn vai trò khác).
// Đọc: api.v_my_cvs, api.v_my_cv_skills, api.v_skills; lưu: api.confirm_cv_profile (migration 0010).
// RLS chỉ cho thấy CV của chính mình, nên cv_id của người khác ra 404.
// File CV gốc (PDF xem cạnh danh sách kỹ năng, DOCX chỉ tải về) đi qua route ../tep (signed URL 5 phút).

const TITLE = "Kiểm tra lại những gì hệ thống đọc được";

type SkillRow = {
  skill_id: number;
  slug: string;
  name: string;
  evidence_level: EvidenceLevel;
  evidence: string | null;
  years: number | null;
  confirmed: boolean;
};
type TaxonomyRow = { id: number; slug: string; name: string; aliases: string[] | null };
type CvRow = {
  id: string;
  mime: string;
  parse_status: string;
  created_at: string;
  original_name: string | null;
  years_exp: number | string | null; // numeric của Postgres có thể về dạng chuỗi
  target_title: string | null;
  profile_confirmed_at: string | null;
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default async function ConfirmCvPage({ params }: PageProps<"/ho-so/[cvId]/xac-nhan">) {
  const { cvId } = await params;
  await requireAccess(`/ho-so/${cvId}/xac-nhan`);

  if (!isUuid(cvId)) notFound();

  const api = (await createClient()).schema("api");
  const cv = await api
    .from("v_my_cvs")
    .select("id, mime, parse_status, created_at, original_name, years_exp, target_title, profile_confirmed_at")
    .eq("id", cvId)
    .maybeSingle<CvRow>();
  if (cv.error) return <NotReady text="Chưa đọc được CV của bạn, hãy tải lại trang." />;
  if (!cv.data) notFound();

  const fileLabel = cv.data.original_name ?? `CV ${cv.data.mime.includes("pdf") ? "PDF" : "DOCX"}`;
  const uploaded = `${fileLabel} · tải lúc ${formatTime(cv.data.created_at)}`;

  if (cv.data.parse_status !== "parsed") {
    return (
      <PageShell title={TITLE}>
        <div className="grid max-w-3xl gap-4">
          <p className="text-sm text-muted-foreground">{uploaded}</p>
          <ParsePending cvId={cvId} status={cv.data.parse_status} />
        </div>
      </PageShell>
    );
  }

  const [skills, taxonomy] = await Promise.all([
    api
      .from("v_my_cv_skills")
      .select("skill_id, slug, name, evidence_level, evidence, years, confirmed")
      .eq("cv_id", cvId)
      .returns<SkillRow[]>(),
    api.from("v_skills").select("id, slug, name, aliases").order("name").returns<TaxonomyRow[]>(),
  ]);
  if (skills.error || taxonomy.error) {
    const missing = skills.error?.code === "PGRST205" || taxonomy.error?.code === "PGRST205";
    return (
      <NotReady
        text={
          missing
            ? "Database chưa có api.v_my_cv_skills / api.v_skills (migration 0010). Báo nhóm chạy migration rồi tải lại trang."
            : "Chưa đọc được hồ sơ kỹ năng, hãy tải lại trang."
        }
      />
    );
  }

  const initialSkills: CvSkill[] = (skills.data ?? []).map((r) => ({
    skillId: r.skill_id,
    slug: r.slug,
    name: r.name,
    level: r.evidence_level,
    evidence: r.evidence,
    years: r.years == null ? null : Number(r.years),
    confirmed: r.confirmed,
  }));
  const skillTaxonomy: TaxonomySkill[] = (taxonomy.data ?? []).map((r) => ({
    id: r.id,
    slug: r.slug,
    name: r.name,
    aliases: r.aliases ?? [],
  }));

  const pdf = cvExtension(cv.data.mime) === "pdf";
  const form = (
    <SkillConfirmForm
      cvId={cvId}
      initialSkills={initialSkills}
      taxonomy={skillTaxonomy}
      initialYears={cv.data.years_exp == null ? null : Number(cv.data.years_exp)}
      initialTitle={cv.data.target_title}
      confirmedLabel={cv.data.profile_confirmed_at ? formatTime(cv.data.profile_confirmed_at) : null}
    />
  );

  // DOCX: không xem được trong trình duyệt, chỉ có ô tải về nên giữ một cột.
  if (!pdf) {
    return (
      <PageShell title={TITLE}>
        <div className="grid max-w-3xl gap-4">
          <p className="text-sm text-muted-foreground">{uploaded}</p>
          <CvOriginal cvId={cvId} fileLabel={fileLabel} pdf={false} />
          {form}
        </div>
      </PageShell>
    );
  }

  // PDF: desktop 2 cột (kỹ năng | CV gốc, CV dính theo khi cuộn); mobile xếp dọc, CV ở dưới.
  return (
    <PageShell title={TITLE}>
      <p className="text-sm text-muted-foreground">{uploaded}</p>
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="min-w-0">{form}</div>
        <CvOriginal cvId={cvId} fileLabel={fileLabel} pdf className="min-w-0 lg:sticky lg:top-4" />
      </div>
    </PageShell>
  );
}

function NotReady({ text }: { text: string }) {
  return (
    <PageShell title={TITLE}>
      <Alert variant="destructive" className="max-w-3xl">
        <AlertTitle>Chức năng xác nhận hồ sơ chưa sẵn sàng</AlertTitle>
        <AlertDescription>{text}</AlertDescription>
      </Alert>
    </PageShell>
  );
}
