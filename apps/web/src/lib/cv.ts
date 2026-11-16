// Quy tắc file CV dùng chung cho server action và form tải CV (S3-T02, US-11).
// Giới hạn khớp với bucket `cvs` và ràng buộc của app.cvs trong migration 0001.

export const CV_BUCKET = "cvs";
export const CV_MAX_BYTES = 5 * 1024 * 1024;

const EXT_BY_MIME: Record<string, "pdf" | "docx"> = {
  "application/pdf": "pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
};

/** Đuôi file theo MIME; null khi không phải PDF/DOCX. */
export function cvExtension(mime: string): "pdf" | "docx" | null {
  return EXT_BY_MIME[mime] ?? null;
}

/** Đường dẫn trong bucket: u/{uid}/{cvId}.{ext}. Policy cv_files_seeker dựa vào thư mục u/{uid}/. */
export function cvStoragePath(userId: string, cvId: string, ext: "pdf" | "docx"): string {
  return `u/${userId}/${cvId}.${ext}`;
}

/** SHA-256 dạng hex 64 ký tự (Web Crypto: chạy được cả Node lẫn Cloudflare Workers). */
export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}
