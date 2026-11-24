"use client";

import { ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState, useTransition } from "react";
import { useDismiss } from "@/components/match/use-dismiss";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { WORK_MODE_LABEL } from "@/lib/jobs/filters";
import { POPULAR_PROVINCES, PROVINCES, provinceName, unaccent } from "@/lib/jobs/provinces";
import { MATCH_WORK_MODES, matchHref, TOP_N_OPTIONS, type MatchParams } from "@/lib/match";
import { cn } from "@/lib/utils";

export type CvOption = { id: string; label: string; isPrimary: boolean; confirmed: boolean };

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * Thanh chọn CV, số việc, tỉnh, hình thức (S4-H01 · docs/ui/wireframe_matches.png màn 1).
 * Đổi lựa chọn chưa chấm lại ngay: bấm "Tìm việc phù hợp" mới ghi lên URL (API giới hạn 20 lượt/phút).
 * Trang cha đặt `key` theo URL nên state ở đây luôn khớp URL sau mỗi lần điều hướng.
 */
export function MatchFilters({ params, cvs }: { params: MatchParams & { cvId: string }; cvs: CvOption[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [draft, setDraft] = useState(params);
  const changed = matchHref(draft) !== matchHref(params);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    startTransition(() => router.push(matchHref(draft), { scroll: false }));
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Chọn CV và bộ lọc"
      className="grid gap-x-6 gap-y-4 rounded-lg border bg-muted/30 p-4 text-sm md:grid-cols-[minmax(14rem,1.2fr)_auto_minmax(12rem,1fr)] lg:grid-cols-[minmax(14rem,1.2fr)_auto_minmax(12rem,1fr)_auto_auto]"
    >
      <label className="grid content-start gap-1.5">
        <span className="font-medium">CV dùng để chấm</span>
        <select
          className="h-8 w-full rounded-lg border border-input bg-background px-2"
          value={draft.cvId}
          onChange={(e) => setDraft({ ...draft, cvId: e.target.value })}
        >
          {cvs.map((cv) => (
            <option key={cv.id} value={cv.id}>
              {cv.isPrimary ? "★ " : ""}
              {cv.label}
              {cv.confirmed ? "" : " (chưa xác nhận)"}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="grid content-start gap-1.5">
        <legend className="mb-1.5 font-medium">Số việc</legend>
        <div className="inline-flex h-8 w-fit overflow-hidden rounded-lg border border-input">
          {TOP_N_OPTIONS.map((n) => (
            <label
              key={n}
              className={cn(
                "flex cursor-pointer items-center border-l border-input px-3 first:border-l-0 has-focus-visible:ring-2 has-focus-visible:ring-ring",
                draft.topN === n ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted",
              )}
            >
              <input
                type="radio"
                name="n"
                className="sr-only"
                checked={draft.topN === n}
                onChange={() => setDraft({ ...draft, topN: n })}
              />
              {n}
            </label>
          ))}
        </div>
      </fieldset>

      <ProvincePicker value={draft.provinces} onChange={(provinces) => setDraft({ ...draft, provinces })} />

      <fieldset className="grid content-start gap-1.5">
        <legend className="mb-1.5 font-medium">Hình thức</legend>
        <div className="flex flex-wrap gap-x-3 gap-y-1.5">
          {MATCH_WORK_MODES.map((m) => (
            <label key={m} className="flex h-8 items-center gap-2">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={draft.modes.includes(m)}
                onChange={() => setDraft({ ...draft, modes: toggle(draft.modes, m) })}
              />
              {WORK_MODE_LABEL[m]}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid content-end gap-1">
        <Button type="submit" disabled={pending} className="h-8">
          {pending ? "Đang tìm…" : "Tìm việc phù hợp"}
        </Button>
      </div>

      <p className="text-xs text-muted-foreground md:col-span-full">
        Mặc định chọn CV chính (★), chỉ hiện CV đã đọc xong. Tin làm từ xa (Remote) và tin không ghi tỉnh luôn có trong
        kết quả dù lọc tỉnh.
        {changed && <b className="text-foreground"> Bấm &quot;Tìm việc phù hợp&quot; để chấm lại theo lựa chọn mới.</b>}
      </p>
    </form>
  );
}

/** Ô chọn nhiều tỉnh dạng thả xuống: chip tỉnh đã chọn, ô tìm không dấu, danh sách tỉnh. */
function ProvincePicker({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const q = unaccent(query);

  useDismiss(box, open, useCallback(() => setOpen(false), []));
  const visible = q
    ? PROVINCES.filter((p) => unaccent(p.name).includes(q))
    : [
        ...PROVINCES.filter((p) => POPULAR_PROVINCES.includes(p.code) || value.includes(p.code)),
        ...PROVINCES.filter((p) => !POPULAR_PROVINCES.includes(p.code) && !value.includes(p.code)),
      ];

  return (
    <div ref={box} className="relative grid content-start gap-1.5">
      <span className="font-medium" id="match-province-label">
        Tỉnh / thành
      </span>
      <button
        type="button"
        aria-expanded={open}
        aria-labelledby="match-province-label"
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-8 w-full items-center gap-1 rounded-lg border border-input bg-background px-2 py-1 text-left"
      >
        <span className="flex flex-1 flex-wrap gap-1">
          {value.length === 0 ? (
            <span className="text-muted-foreground">Mọi tỉnh</span>
          ) : (
            value.map((code) => (
              <span key={code} className="rounded-full bg-primary px-2 text-xs leading-5 text-primary-foreground">
                {provinceName(code)}
              </span>
            ))
          )}
        </span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </button>
      {open && (
        <div className="absolute top-full z-10 mt-1 grid w-full min-w-60 gap-2 rounded-lg border bg-background p-3 shadow-md">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm tỉnh… (gõ không dấu)"
            aria-label="Tìm tỉnh/thành"
            className="h-8"
            autoFocus
          />
          <div className="grid max-h-56 gap-1.5 overflow-y-auto">
            {visible.map((p) => (
              <label key={p.code} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={value.includes(p.code)}
                  onChange={() => onChange(toggle(value, p.code))}
                />
                {p.name}
              </label>
            ))}
            {visible.length === 0 && <p className="text-muted-foreground">Không thấy tỉnh nào.</p>}
          </div>
          <div className="flex justify-between gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange([])} disabled={value.length === 0}>
              Bỏ chọn
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
              Xong
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
