"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  formatMillion,
  hasFilters,
  jobsHref,
  LEVEL_LABEL,
  LEVELS,
  SALARY_STEPS,
  WORK_MODE_LABEL,
  WORK_MODES,
  type JobFilters as Filters,
} from "@/lib/jobs/filters";
import { POPULAR_PROVINCES, PROVINCES, unaccent } from "@/lib/jobs/provinces";
import { cn } from "@/lib/utils";

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * Cột bộ lọc (S2-H03). Mỗi lần đổi là ghi lên URL ngay, về trang 1; trang server đọc URL
 * để tìm. Trang cha đặt `key` theo URL nên state ở đây luôn khớp URL sau mỗi lần điều hướng.
 */
export function JobFilters({ filters }: { filters: Filters }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [draft, setDraft] = useState(filters);
  const [open, setOpen] = useState(false);
  const [provinceQuery, setProvinceQuery] = useState("");
  const [showAllProvinces, setShowAllProvinces] = useState(false);

  function apply(patch: Partial<Filters>) {
    const next = { ...draft, ...patch, page: 1 };
    setDraft(next);
    startTransition(() => router.push(jobsHref(next), { scroll: false }));
  }

  const query = unaccent(provinceQuery);
  const visibleProvinces = query
    ? PROVINCES.filter((p) => unaccent(p.name).includes(query))
    : showAllProvinces
      ? PROVINCES
      : PROVINCES.filter(
          (p) => POPULAR_PROVINCES.includes(p.code) || draft.provinces.includes(p.code),
        );

  const activeCount =
    draft.provinces.length + draft.modes.length + draft.levels.length + (draft.salaryMin ? 1 : 0);

  return (
    <aside aria-label="Bộ lọc việc làm" className="md:sticky md:top-4 md:self-start">
      <Button
        type="button"
        variant="outline"
        className="w-full md:hidden"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        Bộ lọc{activeCount ? ` (${activeCount})` : ""}
      </Button>

      <div
        className={cn(
          "mt-3 grid gap-5 rounded-lg border bg-muted/30 p-4 text-sm md:mt-0 md:grid",
          open ? "grid" : "hidden",
          pending && "opacity-60",
        )}
        aria-busy={pending}
      >
        <fieldset className="grid gap-2">
          <legend className="mb-1 font-medium">Tỉnh/thành</legend>
          <Input
            value={provinceQuery}
            onChange={(e) => setProvinceQuery(e.target.value)}
            placeholder="Tìm tỉnh… (gõ không dấu)"
            aria-label="Tìm tỉnh/thành"
            className="h-8"
          />
          <div className="grid max-h-56 gap-1.5 overflow-y-auto">
            {visibleProvinces.map((p) => (
              <Check
                key={p.code}
                label={p.name}
                checked={draft.provinces.includes(p.code)}
                onChange={() => apply({ provinces: toggle(draft.provinces, p.code) })}
              />
            ))}
            {visibleProvinces.length === 0 && (
              <p className="text-muted-foreground">Không thấy tỉnh nào.</p>
            )}
          </div>
          {!query && (
            <button
              type="button"
              className="justify-self-start text-xs text-primary underline-offset-2 hover:underline"
              onClick={() => setShowAllProvinces((s) => !s)}
            >
              {showAllProvinces ? "Thu gọn" : `Xem tất cả ${PROVINCES.length} tỉnh/thành`}
            </button>
          )}
        </fieldset>

        <fieldset className="grid gap-1.5">
          <legend className="mb-1 font-medium">Lương tối thiểu</legend>
          {[null, ...SALARY_STEPS].map((step) => (
            <label key={step ?? "all"} className="flex items-center gap-2">
              <input
                type="radio"
                name="luong"
                className="size-4 accent-primary"
                checked={draft.salaryMin === step}
                onChange={() => apply({ salaryMin: step })}
              />
              {step ? `Từ ${formatMillion(step)}` : "Tất cả"}
            </label>
          ))}
          <p className="text-xs text-muted-foreground">
            Chọn mức lương sẽ ẩn tin không công bố lương.
          </p>
        </fieldset>

        <fieldset className="grid gap-1.5">
          <legend className="mb-1 font-medium">Hình thức làm việc</legend>
          {WORK_MODES.map((m) => (
            <Check
              key={m}
              label={WORK_MODE_LABEL[m]}
              checked={draft.modes.includes(m)}
              onChange={() => apply({ modes: toggle(draft.modes, m) })}
            />
          ))}
        </fieldset>

        <fieldset className="grid gap-1.5">
          <legend className="mb-1 font-medium">Cấp bậc</legend>
          <div className="grid grid-cols-2 gap-1.5">
            {LEVELS.map((l) => (
              <Check
                key={l}
                label={LEVEL_LABEL[l]}
                checked={draft.levels.includes(l)}
                onChange={() => apply({ levels: toggle(draft.levels, l) })}
              />
            ))}
          </div>
        </fieldset>

        {hasFilters(draft) && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => apply({ provinces: [], salaryMin: null, modes: [], levels: [] })}
          >
            Xóa tất cả bộ lọc
          </Button>
        )}
      </div>
    </aside>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex items-center gap-2">
      <input
        type="checkbox"
        className="size-4 accent-primary"
        checked={checked}
        onChange={onChange}
      />
      {label}
    </label>
  );
}
