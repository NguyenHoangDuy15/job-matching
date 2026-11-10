import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import {
  EMPTY_FILTERS,
  formatMillion,
  hasFilters,
  jobsHref,
  LEVEL_LABEL,
  PAGE_SIZE,
  WORK_MODE_LABEL,
  type JobFilters,
} from "@/lib/jobs/filters";
import { provinceName } from "@/lib/jobs/provinces";
import { searchJobs, type SearchResult } from "@/lib/jobs/search";
import { cn } from "@/lib/utils";
import { JobCard } from "./job-card";

type Chip = { label: string; href: string };

/** Mỗi bộ lọc đang bật thành một chip, bấm để bỏ riêng bộ lọc đó. */
export function filterChips(f: JobFilters): Chip[] {
  const without = (patch: Partial<JobFilters>) => jobsHref({ ...f, ...patch, page: 1 });
  return [
    ...(f.q ? [{ label: `"${f.q}"`, href: without({ q: "" }) }] : []),
    ...f.provinces.map((code) => ({
      label: provinceName(code),
      href: without({ provinces: f.provinces.filter((c) => c !== code) }),
    })),
    ...(f.salaryMin ? [{ label: `≥ ${formatMillion(f.salaryMin)}`, href: without({ salaryMin: null }) }] : []),
    ...(f.modes.length
      ? [{ label: f.modes.map((m) => WORK_MODE_LABEL[m]).join(", "), href: without({ modes: [] }) }]
      : []),
    ...(f.levels.length
      ? [{ label: f.levels.map((l) => LEVEL_LABEL[l]).join(", "), href: without({ levels: [] }) }]
      : []),
  ];
}

export function ActiveFilters({ filters }: { filters: JobFilters }) {
  const chips = filterChips(filters);
  if (!chips.length) return null;
  return (
    <ul aria-label="Bộ lọc đang bật" className="flex flex-wrap gap-2">
      {chips.map((c) => (
        <li key={c.href}>
          <Link
            href={c.href}
            scroll={false}
            className="inline-flex items-center gap-1 rounded-full border px-3 py-0.5 text-xs hover:bg-muted"
            aria-label={`Bỏ bộ lọc ${c.label}`}
          >
            {c.label} <span aria-hidden>×</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Phần danh sách: gọi DB nên nằm trong Suspense, trang cha hiện skeleton trong lúc chờ. */
export async function JobResults({ filters }: { filters: JobFilters }) {
  let result: SearchResult;
  try {
    result = await searchJobs(filters);
  } catch (err) {
    console.error(err);
    return (
      <div role="alert" className="grid justify-items-start gap-3 rounded-lg border p-6">
        <p>Chưa tải được danh sách việc, thử lại.</p>
        {/* Thẻ <a> thường: tải lại hẳn trang thay vì dùng bộ nhớ đệm của router. */}
        <a href={jobsHref(filters)} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Thử lại
        </a>
      </div>
    );
  }

  const { jobs, total, hasNext, ms } = result;

  if (jobs.length === 0) {
    return filters.page > 1 ? <PastLastPage filters={filters} /> : <NoResults filters={filters} />;
  }

  const seconds = (ms / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  return (
    <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">
        {total !== null ? <b className="text-foreground">{total.toLocaleString("vi-VN")} việc</b> : `Trang ${filters.page}`}
        {" · "}trong {seconds} giây · {filters.q ? "liên quan nhất trước" : "mới cập nhật trước"}
      </p>
      {jobs.map((job) => (
        <JobCard key={job.public_id} job={job} />
      ))}
      <Pagination filters={filters} total={total} hasNext={hasNext} />
    </div>
  );
}

function NoResults({ filters }: { filters: JobFilters }) {
  const chips = filterChips(filters);
  return (
    <div className="grid justify-items-start gap-3 rounded-lg border p-6">
      <p className="font-medium">
        Không có việc nào khớp{filters.q && <> từ khóa &quot;{filters.q}&quot;</>}
        {hasFilters(filters) && " với bộ lọc hiện tại"}.
      </p>
      {chips.length > 0 && (
        <>
          <p className="text-sm text-muted-foreground">Thử bỏ bớt điều kiện:</p>
          <div className="flex flex-wrap gap-2">
            {chips.map((c) => (
              <Link key={c.href} href={c.href} className={buttonVariants({ variant: "outline", size: "sm" })}>
                Bỏ {c.label}
              </Link>
            ))}
            <Link href={jobsHref(EMPTY_FILTERS)} className={buttonVariants({ size: "sm" })}>
              Xóa tất cả
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

function PastLastPage({ filters }: { filters: JobFilters }) {
  return (
    <div className="grid justify-items-start gap-3 rounded-lg border p-6">
      <p>Không còn việc nào ở trang {filters.page}.</p>
      <Link href={jobsHref({ ...filters, page: 1 })} className={buttonVariants({ variant: "outline", size: "sm" })}>
        Về trang 1
      </Link>
    </div>
  );
}

/** Có tổng thì đánh số trang; không có tổng thì chỉ Trước/Sau. */
function Pagination({
  filters,
  total,
  hasNext,
}: {
  filters: JobFilters;
  total: number | null;
  hasNext: boolean;
}) {
  const page = filters.page;
  const last = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;
  if (page === 1 && !hasNext) return null;

  const href = (p: number) => jobsHref({ ...filters, page: p });
  const numbers = last ? pageWindow(page, last) : [];
  const btn = (active = false) =>
    cn(buttonVariants({ variant: active ? "default" : "outline", size: "sm" }), "min-w-9");

  return (
    <nav aria-label="Phân trang" className="flex flex-wrap items-center gap-1.5 pt-2">
      {page > 1 && (
        <Link href={href(page - 1)} className={btn()} aria-label="Trang trước">
          ‹
        </Link>
      )}
      {last ? (
        numbers.map((n, i) =>
          n === null ? (
            <span key={`gap-${i}`} className="px-1 text-muted-foreground">
              …
            </span>
          ) : (
            <Link key={n} href={href(n)} className={btn(n === page)} aria-current={n === page ? "page" : undefined}>
              {n}
            </Link>
          ),
        )
      ) : (
        <span className="px-2 text-sm">Trang {page}</span>
      )}
      {hasNext && (
        <Link href={href(page + 1)} className={btn()} aria-label="Trang sau">
          ›
        </Link>
      )}
      <span className="ml-2 text-xs text-muted-foreground">{PAGE_SIZE} tin mỗi trang</span>
    </nav>
  );
}

/** 1 … 4 5 [6] 7 8 … 17 */
function pageWindow(page: number, last: number): (number | null)[] {
  const keep = new Set([1, last, page - 2, page - 1, page, page + 1, page + 2]);
  const out: (number | null)[] = [];
  for (let n = 1; n <= last; n++) {
    if (!keep.has(n)) continue;
    const prev = out[out.length - 1];
    if (typeof prev === "number" && n - prev > 1) out.push(null);
    out.push(n);
  }
  return out;
}
