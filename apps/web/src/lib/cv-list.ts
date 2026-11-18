// Danh sách CV của tôi (S3-H04, US-13). Hàm thuần, chạy được cả server lẫn `node --test`.
// Dữ liệu: api.v_my_cvs (0015) + api.v_my_cv_skills (0010).
import type { EvidenceLevel } from "./cv-profile.ts";

export type CvListRow = {
  id: string;
  mime: string;
  parse_status: string; // queued | parsing | parsed | failed
  parse_error: string | null;
  is_primary: boolean;
  created_at: string;
  original_name: string | null;
  years_exp: number | string | null; // numeric của Postgres có thể về dạng chuỗi
  target_title: string | null;
  profile_confirmed_at: string | null;
  delete_after: string | null; // date "2026-12-18"
};

export type SkillCounts = Record<EvidenceLevel, number>;

export type CvStatus = "confirmed" | "unconfirmed" | "queued" | "parsing" | "failed";

export const STATUS_LABEL: Record<CvStatus, string> = {
  confirmed: "Đã xác nhận",
  unconfirmed: "Chưa xác nhận",
  queued: "Chưa phân tích",
  parsing: "Đang phân tích",
  failed: "Lỗi phân tích",
};

/** Trạng thái hiển thị: đã đọc xong thì xét người dùng đã bấm Lưu hồ sơ chưa. */
export function cvStatus(row: Pick<CvListRow, "parse_status" | "profile_confirmed_at">): CvStatus {
  if (row.parse_status === "parsed") return row.profile_confirmed_at ? "confirmed" : "unconfirmed";
  if (row.parse_status === "parsing" || row.parse_status === "failed") return row.parse_status;
  return "queued";
}

/** Đếm kỹ năng theo mức bằng chứng cho từng CV từ các dòng api.v_my_cv_skills. */
export function countSkills(rows: { cv_id: string; evidence_level: EvidenceLevel }[]): Map<string, SkillCounts> {
  const counts = new Map<string, SkillCounts>();
  for (const r of rows) {
    const c = counts.get(r.cv_id) ?? { strong: 0, listed: 0, user_added: 0 };
    c[r.evidence_level] += 1;
    counts.set(r.cv_id, c);
  }
  return counts;
}

/** CV chính đứng đầu, còn lại mới nhất trước. */
export function sortCvs<T extends Pick<CvListRow, "is_primary" | "created_at">>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) => Number(b.is_primary) - Number(a.is_primary) || b.created_at.localeCompare(a.created_at),
  );
}

/** Tên hiện trên danh sách: tên tệp gốc, CV tải trước migration 0010 không có thì ghi loại tệp. */
export function cvLabel(row: Pick<CvListRow, "original_name" | "mime">): string {
  return row.original_name ?? `CV ${row.mime.includes("pdf") ? "PDF" : "DOCX"}`;
}

/** "Backend Developer · 1,5 năm"; thiếu phần nào thì bỏ phần đó, thiếu cả hai thì null. */
export function profileLine(row: Pick<CvListRow, "target_title" | "years_exp">): string | null {
  const years = row.years_exp == null ? null : Number(row.years_exp);
  const parts = [
    row.target_title?.trim() || null,
    years == null || Number.isNaN(years) ? null : `${years.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} năm`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/** Ngày dạng "2026-12-18" → "18/12/2026" (không qua Date để khỏi lệch múi giờ). */
export function formatDay(date: string | null): string | null {
  const m = date?.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : null;
}

/** Mã lỗi app.cvs.parse_error (do API đọc CV ghi) sang câu ngắn cho người dùng. */
export function parseErrorLabel(code: string | null): string {
  switch (code) {
    case "ocr_required":
    case "unreadable_text":
      return "Không đọc được chữ trong CV (có thể là ảnh chụp/scan). Hãy xuất lại PDF từ Word/Google Docs.";
    case "encrypted":
      return "CV có mật khẩu. Hãy bỏ mật khẩu rồi tải lại.";
    case "corrupt_file":
      return "Tệp CV bị hỏng. Hãy xuất lại rồi tải lại.";
    case "unsupported_type":
      return "Định dạng tệp không được hỗ trợ.";
    case "timeout":
      return "Phân tích quá lâu. Hãy xuất lại PDF đơn giản hơn rồi thử lại.";
    default:
      return "Có lỗi khi phân tích CV. Hãy thử phân tích lại.";
  }
}

/** Lỗi của api.set_primary_cv (0015) sang câu cho người dùng. */
export function setPrimaryErrorMessage(err: { code?: string }): string {
  if (err.code === "42501") return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại.";
  if (err.code === "P0002") return "Không tìm thấy CV, hãy tải lại trang.";
  return "Chưa đặt được CV chính, hãy thử lại.";
}
