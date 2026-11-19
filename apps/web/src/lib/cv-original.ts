// Xem lại file CV gốc trên màn xác nhận hồ sơ (S3-H02, US-12). Hàm thuần, chạy được cả `node --test`.
// File nằm trong bucket private `cvs`; route /ho-so/[cvId]/tep tạo signed URL ngắn hạn mỗi lần bấm.
import { cvExtension } from "./cv.ts";

/** Hạn của signed URL (giây). Ngắn: link lộ ra ngoài (lịch sử, chia sẻ nhầm) cũng sớm vô dụng. */
export const CV_SIGNED_URL_TTL = 300;

/** Đường dẫn route trả file gốc: xem trong trình duyệt, hoặc tải về khi `download`. */
export function cvFileHref(cvId: string, download = false): string {
  return `/ho-so/${cvId}/tep${download ? "?tai=1" : ""}`;
}

/**
 * Tên tệp khi tải về: tên gốc người dùng đặt, thiếu đuôi thì thêm đuôi theo MIME.
 * Không có tên gốc (CV tải trước migration 0010) thì dùng "CV.pdf" / "CV.docx".
 */
export function cvDownloadName(originalName: string | null, mime: string): string {
  const ext = cvExtension(mime) ?? "pdf";
  const name = originalName?.trim();
  if (!name) return `CV.${ext}`;
  return name.toLowerCase().endsWith(`.${ext}`) ? name : `${name}.${ext}`;
}
