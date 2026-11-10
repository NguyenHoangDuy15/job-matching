import { Search } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LEVELS, WORK_MODES, type JobFilters } from "@/lib/jobs/filters";
import { cn } from "@/lib/utils";

/**
 * Ô tìm kiếm (form GET thường, chạy cả khi chưa tải JS). Gửi kèm bộ lọc đang bật
 * bằng input ẩn để tìm từ khóa mới không làm mất bộ lọc; số trang về 1.
 */
export function SearchBar({ filters }: { filters: JobFilters }) {
  const hidden: [string, string][] = [
    ["tinh", filters.provinces.join(",")],
    ["luong", filters.salaryMin ? String(filters.salaryMin) : ""],
    ["hinh-thuc", WORK_MODES.filter((m) => filters.modes.includes(m)).join(",")],
    ["cap-bac", LEVELS.filter((l) => filters.levels.includes(l)).join(",")],
  ];

  return (
    <form action="/viec-lam" role="search" className="flex gap-2">
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          type="search"
          name="q"
          defaultValue={filters.q}
          maxLength={100}
          aria-label="Từ khóa tìm việc"
          placeholder="Chức danh, kỹ năng, công ty… (gõ không dấu được)"
          className="h-10 pl-9"
        />
      </div>
      {hidden.map(([name, value]) => value && <input key={name} type="hidden" name={name} value={value} />)}
      <button type="submit" className={cn(buttonVariants({ size: "lg" }), "h-10 px-5")}>
        Tìm
      </button>
    </form>
  );
}
