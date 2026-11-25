"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useCallback, useId, useRef, useState } from "react";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { useDismiss } from "@/components/match/use-dismiss";
import { buttonVariants } from "@/components/ui/button";
import { WORK_MODE_LABEL, type WorkMode } from "@/lib/jobs/filters";
import { daysLeft, daysLeftLabel, formatDay, isExpiringSoon } from "@/lib/jobs/format";
import {
  BASE_WEIGHTS,
  byLevel,
  COMPONENT_INFO,
  COMPONENT_KEYS,
  displayWeights,
  formulaText,
  matchedLabel,
  numberVi,
  type MatchResult,
  type SkillMatched,
} from "@/lib/match";
import { cn } from "@/lib/utils";

/**
 * Thẻ một việc phù hợp (S4-H02 · US-16 · docs/ui/wireframe_matches.png màn 1–2):
 * điểm H + popover "Điểm tính thế nào?", 4 thanh K/M/E/X, kỹ năng khớp / CV chưa thể hiện,
 * hạn nộp, Xem tin, Ứng tuyển ở trang gốc. `sample` = dữ liệu mẫu: tắt các link.
 * Nút Lưu (S4-H05): `saved` = tin đã có trong Việc đã lưu lúc tải trang.
 */
export function MatchCard({ result: r, sample, saved }: { result: MatchResult; sample: boolean; saved: boolean }) {
  const mode = r.work_mode !== "unknown" && r.work_mode in WORK_MODE_LABEL ? WORK_MODE_LABEL[r.work_mode as WorkMode] : null;
  const meta = [r.company, r.provinces.join(", ") || null, mode].filter(Boolean);
  const expiring = isExpiringSoon(r.valid_through);
  const left = r.valid_through ? daysLeft(r.valid_through) : null;
  const matched = byLevel(r.skills_matched);
  const missing = byLevel(r.skills_missing);

  return (
    <article className="grid gap-x-5 gap-y-3 rounded-lg border p-4 sm:grid-cols-[5.5rem_minmax(0,1fr)] lg:grid-cols-[5.5rem_minmax(0,1fr)_19rem]">
      <ScoreBox result={r} />

      <div className="grid min-w-0 content-start gap-1">
        <h3 className="flex flex-wrap items-center gap-2 font-semibold leading-snug">
          {r.title}
          {expiring && (
            <span className="rounded border border-destructive px-1.5 text-xs font-medium text-destructive">
              Sắp hết hạn
            </span>
          )}
        </h3>
        <p className="text-sm text-muted-foreground">
          {meta.join(" · ")}
          {r.valid_through && left != null && (
            <>
              {meta.length > 0 && " · "}Hạn nộp {formatDay(r.valid_through)} ({daysLeftLabel(left)})
            </>
          )}
        </p>
      </div>

      <div className="flex flex-wrap content-start gap-2 sm:col-start-2 lg:col-start-3 lg:row-start-1 lg:justify-end">
        {r.public_id && <SaveJobButton publicId={r.public_id} initialSaved={saved} disabled={sample} />}
        {sample || !r.public_id ? (
          <span className={cn(buttonVariants({ variant: "outline", size: "sm" }), "opacity-50")} title="Dữ liệu mẫu">
            Xem tin
          </span>
        ) : (
          <Link href={`/viec-lam/${r.public_id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Xem tin
          </Link>
        )}
        {r.apply_url &&
          (sample ? (
            <span className={cn(buttonVariants({ size: "sm" }), "opacity-50")} title="Dữ liệu mẫu">
              Ứng tuyển ở trang gốc <ExternalLink aria-hidden />
            </span>
          ) : (
            <a href={r.apply_url} target="_blank" rel="noopener noreferrer" className={buttonVariants({ size: "sm" })}>
              Ứng tuyển ở trang gốc <ExternalLink aria-hidden />
            </a>
          ))}
      </div>

      <ComponentBars result={r} />

      <div className="grid content-start gap-2 text-sm sm:col-start-2 lg:col-start-3 lg:row-start-2">
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 text-xs font-medium">Khớp</span>
          {matched.length ? (
            matched.map((s) => <MatchedChip key={`${s.skill_id}-${s.via ?? ""}`} skill={s} />)
          ) : (
            <span className="text-xs text-muted-foreground">chưa khớp kỹ năng nào</span>
          )}
        </div>
        {missing.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-xs font-medium">CV chưa thể hiện</span>
            {missing.map((s) => (
              <span
                key={s.skill_id}
                className="rounded-full border border-destructive/60 bg-destructive/5 px-2 text-xs leading-5 text-destructive"
              >
                {s.skill} · {s.level === "required" ? "bắt buộc" : "ưu tiên"}
              </span>
            ))}
          </div>
        )}
      </div>

      <p className="text-xs text-muted-foreground sm:col-start-2 lg:col-span-2">{r.explanation}</p>
    </article>
  );
}

const EVIDENCE_TEXT: Record<NonNullable<SkillMatched["evidence"]>, string> = {
  strong: "có bằng chứng trong CV",
  listed: "CV chỉ liệt kê",
  user_added: "bạn tự thêm",
};

function MatchedChip({ skill: s }: { skill: SkillMatched }) {
  const title = [s.level === "required" ? "Bắt buộc" : "Ưu tiên", s.evidence ? EVIDENCE_TEXT[s.evidence] : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <span
      title={title}
      className={cn(
        "rounded-full border px-2 text-xs leading-5",
        s.evidence === "strong" && "border-primary bg-primary text-primary-foreground",
        s.evidence === "listed" && "border-dashed border-foreground/50",
        s.evidence === "user_added" && "border-dotted border-foreground/50 bg-muted",
        s.evidence == null && "border-foreground/30",
      )}
    >
      {matchedLabel(s)}
    </span>
  );
}

function ComponentBars({ result: r }: { result: MatchResult }) {
  return (
    <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)_5.5rem] items-center gap-x-2 gap-y-1.5 text-xs sm:col-start-2">
      {COMPONENT_KEYS.map((k) => {
        const v = r.components[k];
        const label = `${k} · ${COMPONENT_INFO[k].label}`;
        return (
          <div key={k} className="contents">
            <dt className={cn(v == null && "text-muted-foreground")}>{label}</dt>
            <dd aria-hidden className="m-0">
              {v == null ? (
                <div className="h-2 rounded-full border border-dashed border-muted-foreground/50" />
              ) : (
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(v * 100)}%` }} />
                </div>
              )}
            </dd>
            <dd className={cn("m-0 tabular-nums", v == null ? "text-muted-foreground" : "font-medium")}>
              {v == null ? "không áp dụng" : numberVi(v, 2)}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function ScoreBox({ result: r }: { result: MatchResult }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const popId = useId();
  useDismiss(box, open, useCallback(() => setOpen(false), []));

  const weights = displayWeights(r);
  const dropped = COMPONENT_KEYS.filter((k) => r.components[k] == null);

  return (
    <div
      ref={box}
      className="relative flex items-baseline gap-2 sm:row-span-3 sm:grid sm:content-start sm:justify-items-center sm:gap-0 sm:border-r sm:pr-4"
    >
      <span className="text-xs text-muted-foreground">#{r.rank}</span>
      <span className="text-3xl font-bold tabular-nums">{numberVi(r.score, 1)}</span>
      <span className="text-xs text-muted-foreground">/ 100</span>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={popId}
        onClick={() => setOpen((o) => !o)}
        className="ml-auto text-xs text-primary underline underline-offset-2 sm:ml-0 sm:mt-1 sm:text-center"
      >
        Điểm tính thế nào?
      </button>

      {open && (
        <div
          id={popId}
          role="dialog"
          aria-label={`Cách tính điểm ${numberVi(r.score, 1)}`}
          className="absolute left-0 top-full z-20 mt-2 grid w-[min(30rem,calc(100vw-3rem))] gap-2 rounded-lg border bg-background p-3 text-left text-xs shadow-lg"
        >
          <p className="rounded-md bg-primary px-2.5 py-2 text-primary-foreground">
            <b>
              Điểm {numberVi(r.score, 1)} = {formulaText(weights)}
            </b>
            {dropped.length > 0 && (
              <>
                <br />
                Không xác định được {dropped.map((k) => `${k} (${COMPONENT_INFO[k].label.toLowerCase()})`).join(", ")} nên bỏ
                phần này và chia lại trọng số của các phần còn lại (tổng vẫn bằng 1).
              </>
            )}
          </p>
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-1 pr-2 text-left font-medium">Thành phần</th>
                <th className="py-1 pr-2 text-left font-medium">Nghĩa</th>
                <th className="py-1 pr-2 text-right font-medium">Gốc</th>
                <th className="py-1 text-right font-medium">Tin này</th>
              </tr>
            </thead>
            <tbody>
              {COMPONENT_KEYS.map((k) => {
                const v = r.components[k];
                const w = weights[k];
                return (
                  <tr key={k} className="border-b align-top last:border-0">
                    <td className="py-1 pr-2 font-medium whitespace-nowrap">
                      {k} {COMPONENT_INFO[k].label}
                    </td>
                    <td className="py-1 pr-2">{COMPONENT_INFO[k].meaning}</td>
                    <td className="py-1 pr-2 text-right tabular-nums">{numberVi(BASE_WEIGHTS[k], 2)}</td>
                    <td className="py-1 text-right tabular-nums whitespace-nowrap">
                      {v == null || w == null ? (
                        <span className="text-muted-foreground">không áp dụng</span>
                      ) : (
                        `${numberVi(w, 2)} × ${numberVi(v, 2)}`
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
            Điểm là mức phù hợp theo công thức, không phải xác suất trúng tuyển. Sửa hồ sơ kỹ năng ở{" "}
            <Link href="/ho-so" className="underline underline-offset-2">
              Hồ sơ CV
            </Link>{" "}
            để điểm sát hơn.
          </p>
        </div>
      )}
    </div>
  );
}
