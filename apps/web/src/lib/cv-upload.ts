// Tải CV thẳng từ trình duyệt lên Storage (S3-H01). Chỉ dùng trong Client Component.
// Không qua Server Action: cần % tiến trình, và Server Action mặc định chỉ nhận body ≤ 1 MB.
import { CV_BUCKET } from "@/lib/cv";
import { CV_HEAD_BYTES, uploadErrorMessage } from "@/lib/cv-file";
import { SUPABASE_KEY, SUPABASE_URL } from "@/lib/supabase/env";

/** Vài byte đầu tệp để nhận ra PDF / DOCX thật (checkCvFile). */
export async function fileHead(file: Blob, bytes = CV_HEAD_BYTES): Promise<Uint8Array> {
  return new Uint8Array(await file.slice(0, bytes).arrayBuffer());
}

export class UploadError extends Error {}

/**
 * Tải tệp lên bucket `cvs` qua REST Storage của Supabase. Dùng XMLHttpRequest thay cho
 * supabase-js để có tiến trình (%). Quyền do policy cv_files_seeker kiểm bằng JWT.
 */
export function uploadToStorage(opts: {
  path: string;
  file: File;
  mime: string;
  accessToken: string;
  onProgress: (percent: number) => void;
}): Promise<void> {
  const { path, file, mime, accessToken, onProgress } = opts;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${SUPABASE_URL}/storage/v1/object/${CV_BUCKET}/${path}`);
    xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
    xhr.setRequestHeader("apikey", SUPABASE_KEY);
    xhr.setRequestHeader("Content-Type", mime);
    xhr.setRequestHeader("x-upsert", "false");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve();
        return;
      }
      // Storage hay trả HTTP 400 kèm statusCode thật ("413", "415"…) trong body.
      let status = xhr.status;
      try {
        const inner = Number((JSON.parse(xhr.responseText) as { statusCode?: string | number }).statusCode);
        if (Number.isFinite(inner) && inner >= 400) status = inner;
      } catch {
        // body không phải JSON: giữ mã HTTP
      }
      reject(new UploadError(uploadErrorMessage(status)));
    };
    xhr.onerror = () => reject(new UploadError(uploadErrorMessage(0)));
    xhr.send(file);
  });
}
