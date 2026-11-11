import { ArrowLeft, ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { buttonVariants } from "@/components/ui/button";
import { getJobDetail, jdSections, type JobDetail, type JobSkill } from "@/lib/jobs/detail";
import { LEVEL_LABEL, WORK_MODE_LABEL } from "@/lib/jobs/filters";
import { JobProvenance } from "@/components/jobs/job-provenance";
import { daysLeft, daysLeftLabel, formatDay, formatSalary, salaryFull } from "@/lib/jobs/format";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { cn } from "@/lib/utils";

// S2-H04 (trang) + S2-H05 (hạn nộp, độ mới, nguồn) · US-06 · docs/ui/wireframe_jobs.png (màn 3).
// Khách và mọi vai trò đều xem được.

// generateMetadata và trang cùng cần dữ liệu: cache() để chỉ gọi DB một lần mỗi request.
const loadJob = cache(getJobDetail);

export async function generateMetadata({ params }: PageProps<"/viec-lam/[id]">): Promise<Metadata> {
  const { id } = await params;
  if (!isSupabaseConfigured) return { title: "Chi tiết việc làm" };
  const result = await loadJob(id).catch(() => null);
  if (!result) return { title: "Không tìm thấy việc làm" };
  const { job } = result;
  return { title: job.company_name ? `${job.title} · ${job.company_name}` : job.title };
}

export default async function JobDetailPage({ params }: PageProps<"/viec-lam/[id]">) {
  const { id } = await params;
  if (!isSupabaseConfigured) notFound();

  let result: Awaited<ReturnType<typeof getJobDetail>>;
  try {
    result = await loadJob(id);
  } catch (err) {
    console.error(err);
    return (
      <Shell>
        <div role="alert" className="grid justify-items-start gap-3 rounded-lg border p-6">
          <p>Chưa tải được tin tuyển dụng, thử lại.</p>
          <a href={`/viec-lam/${id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Thử lại
          </a>
        </div>
      </Shell>
    );
  }
  if (!result) notFound();

  const { job, skills, complete } = result;
  const sections = jdSections(job);

  return (
    <Shell>
      <JobHeader job={job} />
      <SkillTags skills={skills} />

      {sections.length > 0 ? (
        <div className="grid gap-6">
          {sections.map((s) => (
            <section key={s.key} aria-labelledby={`jd-${s.key}`} className="grid gap-2">
              <h2 id={`jd-${s.key}`} className="text-lg font-semibold">
                {s.title}
              </h2>
              <div className="text-sm leading-relaxed break-words whitespace-pre-line">{s.text.trim()}</div>
            </section>
          ))}
        </div>
      ) : (
        <p className="rounded-lg border p-4 text-sm text-muted-foreground">
          {complete
            ? "Tin này chưa có nội dung mô tả. Xem đầy đủ ở trang tuyển dụng gốc."
            : "Mô tả chi tiết đang được cập nhật. Xem đầy đủ ở trang tuyển dụng gốc."}
        </p>
      )}

      {job.apply_url && (
        <div className="border-t pt-4">
          <ApplyLink url={job.apply_url} />
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6">
      <Link
        href="/viec-lam"
        className="inline-flex items-center gap-1 justify-self-start text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden /> Danh sách việc làm
      </Link>
      {children}
    </div>
  );
}

function JobHeader({ job }: { job: JobDetail }) {
  const meta = [
    job.company_name,
    job.provinces.length ? job.provinces.join(", ") : null,
    job.work_mode !== "unknown" ? WORK_MODE_LABEL[job.work_mode] : null,
    job.seniority !== "unknown" ? LEVEL_LABEL[job.seniority] : null,
    job.years_exp_min ? `≥ ${job.years_exp_min.toLocaleString("vi-VN")} năm kinh nghiệm` : null,
    job.employment_type,
  ].filter(Boolean);

  // S2-H05: hạn nộp kèm số ngày còn lại; ≤ 3 ngày thì gắn nhãn "Sắp hết hạn".
  const days = job.valid_through ? daysLeft(job.valid_through) : null;
  const expiring = job.is_expiring_soon || (days !== null && days >= 0 && days <= 3);
  // Rê chuột lên mức lương: số đầy đủ, hoặc chuỗi gốc của tin; bỏ qua nếu trùng chữ đang hiện.
  const salaryText = formatSalary(job);
  const salaryHintRaw = salaryFull(job) ?? job.salary_raw?.trim();
  const salaryHint = salaryHintRaw && salaryHintRaw !== salaryText ? salaryHintRaw : undefined;

  return (
    <header className="grid gap-4 rounded-lg border p-5">
      <div className="grid gap-1">
        <h1 className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xl leading-tight font-semibold break-words">
          <span>{job.title}</span>
          {expiring && (
            <span className="rounded border border-destructive px-2 py-0.5 text-sm font-medium text-destructive">
              Sắp hết hạn
            </span>
          )}
        </h1>
        {meta.length > 0 && <p className="text-muted-foreground">{meta.join(" · ")}</p>}
      </div>

      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <dt className="text-muted-foreground">Mức lương</dt>
          <dd className="text-base font-semibold" title={salaryHint}>
            {salaryText}
          </dd>
        </div>
        {job.valid_through && days !== null && (
          <div>
            <dt className="text-muted-foreground">Hạn nộp</dt>
            <dd className="text-base font-semibold">
              {formatDay(job.valid_through)}{" "}
              <span className={cn("text-sm font-normal", expiring ? "text-destructive" : "text-muted-foreground")}>
                ({daysLeftLabel(days)})
              </span>
            </dd>
          </div>
        )}
        {job.job_family_name && (
          <div>
            <dt className="text-muted-foreground">Nhóm nghề</dt>
            <dd className="text-base font-semibold">{job.job_family_name}</dd>
          </div>
        )}
      </dl>

      <JobProvenance job={job} />

      <div className="flex flex-wrap gap-2">
        {job.apply_url && <ApplyLink url={job.apply_url} />}
        <span
          className={cn(buttonVariants({ variant: "outline" }), "pointer-events-none opacity-50")}
          aria-disabled="true"
          title="Sắp có (Sprint 5)"
        >
          Chấm độ khớp với CV
        </span>
      </div>
    </header>
  );
}

function ApplyLink({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow" className={buttonVariants()}>
      Ứng tuyển ở trang gốc <ExternalLink className="size-4" aria-hidden />
    </a>
  );
}

/** Kỹ năng bắt buộc / ưu tiên (api.v_job_skills, không có kỹ năng chỉ được nhắc). */
function SkillTags({ skills }: { skills: JobSkill[] }) {
  if (skills.length === 0) return null;
  const groups = [
    { level: "required", title: "Kỹ năng bắt buộc", tag: "border-primary bg-primary text-primary-foreground" },
    { level: "preferred", title: "Kỹ năng ưu tiên", tag: "border-dashed text-foreground" },
  ] as const;

  return (
    <section aria-label="Kỹ năng" className="grid gap-3">
      {groups.map((g) => {
        const items = skills.filter((s) => s.level === g.level);
        if (items.length === 0) return null;
        return (
          <div key={g.level} className="flex flex-wrap items-center gap-2">
            <h2 className="mr-1 text-sm font-medium">{g.title}:</h2>
            <ul className="flex flex-wrap gap-1.5">
              {items.map((s) => (
                <li key={s.skill_slug} className={cn("rounded-full border px-2.5 py-0.5 text-xs", g.tag)}>
                  {s.skill_name}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
