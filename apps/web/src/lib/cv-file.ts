// Kiểm tệp CV trên trình duyệt trước khi tải lên (S3-H01, US-11).
// Giới hạn dùng chung với lib/cv.ts (S3-T02) và bucket `cvs`. Import có đuôi .ts để `node --test` chạy được.
import { CV_MAX_BYTES } from "./cv.ts";

export const MAX_CVS = 5;

export const CV_TYPES = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
} as const;
export type CvKind = keyof typeof CV_TYPES;

/** Giá trị cho thuộc tính accept của <input type="file">. */
export const CV_ACCEPT = `.pdf,.docx,${CV_TYPES.pdf},${CV_TYPES.docx}`;

export type CvFileInfo = { name: string; size: number };
export type CvCheck = { ok: true; kind: CvKind; mime: string } | { ok: false; error: string };

const PDF_MAGIC = [0x25, 0x50, 0x44, 0x46, 0x2d]; // "%PDF-"
const ZIP_MAGIC = [0x50, 0x4b, 0x03, 0x04]; // DOCX là gói zip
const OLE_MAGIC = [0xd0, 0xcf, 0x11, 0xe0]; // .doc đời cũ
const OLD_DOC = "Tệp .doc đời cũ chưa hỗ trợ. Hãy lưu lại thành .docx hoặc PDF.";

/** Số byte đầu tệp cần đọc: chuẩn PDF cho phép "%PDF-" nằm trong 1024 byte đầu (có tệp mở đầu bằng dòng trống). */
export const CV_HEAD_BYTES = 1024;

function startsWith(head: Uint8Array, magic: number[], at = 0): boolean {
  return magic.every((b, i) => head[at + i] === b);
}

function hasPdfHeader(head: Uint8Array): boolean {
  const last = Math.min(head.length, CV_HEAD_BYTES) - PDF_MAGIC.length;
  for (let at = 0; at <= last; at++) if (startsWith(head, PDF_MAGIC, at)) return true;
  return false;
}

function extension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

/**
 * Kiểm đuôi, dung lượng và vài byte đầu tệp (ảnh đổi đuôi .png → .pdf vẫn bị chặn).
 * Không tin file.type: trình duyệt suy ra từ đuôi, có khi để trống với .docx.
 * `head` là CV_HEAD_BYTES byte đầu của tệp (ít hơn nếu tệp nhỏ).
 */
export function checkCvFile(file: CvFileInfo, head: Uint8Array): CvCheck {
  const ext = extension(file.name);
  if (ext === "doc") return { ok: false, error: OLD_DOC };
  if (ext !== "pdf" && ext !== "docx") return { ok: false, error: "Chỉ nhận PDF hoặc DOCX." };
  if (file.size === 0) return { ok: false, error: "Tệp rỗng, hãy chọn tệp khác." };
  if (file.size > CV_MAX_BYTES) return { ok: false, error: "Tệp quá lớn (tối đa 5 MB)." };

  const kind: CvKind = ext;
  if (startsWith(head, OLE_MAGIC)) return { ok: false, error: OLD_DOC };
  const realKind = startsWith(head, ZIP_MAGIC) ? "docx" : hasPdfHeader(head) ? "pdf" : null;
  if (realKind !== kind) {
    return { ok: false, error: `Nội dung tệp không phải ${kind.toUpperCase()} (có thể đã bị đổi đuôi).` };
  }
  return { ok: true, kind, mime: CV_TYPES[kind] };
}

/** 1.258.291 byte → "1,2 MB"; dưới 1 MB tính theo KB. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024)).toLocaleString("vi-VN")} KB`;
}

/**
 * Lỗi của api.register_cv (migration 0008, S3-T02) sang câu cho người dùng.
 * 23505: trùng tệp (unique cvs_dedup_file_idx). 23514: thiếu consent hoặc điều khoản đã đổi
 * (thông báo tiếng Việt từ DB). 42501: hết phiên. 53400: đã đủ 5 CV (trigger của migration 0010).
 */
export function registerErrorMessage(err: { code?: string; message?: string }): string {
  if (err.code === "23505") return "CV này bạn đã tải trước đó.";
  if (err.code === "53400") return "Bạn đã có 5 CV. Hãy xóa bớt một CV rồi tải lại.";
  if (err.code === "42501") return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại.";
  if (err.code === "23514" && err.message && /điều khoản/i.test(err.message)) return err.message;
  return "Chưa lưu được CV, hãy thử lại.";
}

/** Mã HTTP khi tải tệp lên Supabase Storage sang câu cho người dùng. */
export function uploadErrorMessage(status: number): string {
  if (status === 413) return "Tệp quá lớn (tối đa 5 MB).";
  if (status === 415) return "Chỉ nhận PDF hoặc DOCX.";
  if (status === 401 || status === 403) return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại.";
  if (status === 409) return "Tệp này đã được tải lên, hãy thử lại.";
  if (status === 0) return "Mất kết nối mạng khi tải lên. Hãy kiểm tra mạng rồi thử lại.";
  return "Tải lên không thành công, hãy thử lại.";
}
