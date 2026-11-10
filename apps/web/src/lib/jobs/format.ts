// Định dạng hiển thị cho thẻ việc làm. Giờ và ngày luôn theo giờ Việt Nam,
// dù trang render trên server Cloudflare ở múi giờ UTC.
const TZ = "Asia/Ho_Chi_Minh";

function million(vnd: number): string {
  return (vnd / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

export function formatSalary(job: {
  salary_min_vnd: number | null;
  salary_max_vnd: number | null;
  salary_raw: string | null;
}): string {
  const { salary_min_vnd: min, salary_max_vnd: max } = job;
  if (min && max) return min === max ? `${million(min)} triệu` : `${million(min)}–${million(max)} triệu`;
  if (min) return `Từ ${million(min)} triệu`;
  if (max) return `Đến ${million(max)} triệu`;
  return job.salary_raw?.trim() || "Thỏa thuận";
}

/** "2026-11-14" → "14/11". Đọc thẳng chuỗi ngày để không lệch múi giờ. */
export function formatDay(isoDate: string): string {
  const [, m, d] = isoDate.split("-");
  return `${d}/${m}`;
}

const updatedFmt = new Intl.DateTimeFormat("vi-VN", {
  timeZone: TZ,
  hour: "2-digit",
  minute: "2-digit",
  day: "2-digit",
  month: "2-digit",
});

/** "02:15 10/11" */
export function formatUpdatedAt(timestamp: string): string {
  const parts = Object.fromEntries(
    updatedFmt.formatToParts(new Date(timestamp)).map((p) => [p.type, p.value]),
  );
  return `${parts.hour}:${parts.minute} ${parts.day}/${parts.month}`;
}

/** Ngày hôm nay ở Việt Nam, dạng "YYYY-MM-DD". */
export function todayVN(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(now);
}

/** Còn ≤ 3 ngày là hết hạn (giống cột is_expiring_soon của api.v_open_jobs). */
export function isExpiringSoon(validThrough: string | null, today = todayVN()): boolean {
  if (!validThrough) return false;
  const days = (Date.parse(validThrough) - Date.parse(today)) / 86_400_000;
  return days >= 0 && days <= 3;
}

const SOURCE_NAMES: Record<string, string> = {
  "vietnamworks.com": "VietnamWorks",
  "topcv.vn": "TopCV",
  "itviec.com": "ITviec",
  "careerviet.vn": "CareerViet",
  "careerlink.vn": "CareerLink",
};

/** Tên trang nguồn lấy từ link tin gốc. */
export function sourceName(url: string | null): string | null {
  if (!url) return null;
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    const known = Object.keys(SOURCE_NAMES).find((d) => host === d || host.endsWith(`.${d}`));
    return known ? SOURCE_NAMES[known] : host;
  } catch {
    return null;
  }
}
