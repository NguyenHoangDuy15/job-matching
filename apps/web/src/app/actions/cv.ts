"use server";

import { revalidatePath } from "next/cache";
import { CV_BUCKET, CV_MAX_BYTES, cvExtension, cvStoragePath, isUuid, sha256Hex } from "@/lib/cv";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

export type CvFormState = {
  error?: string;
  message?: string;
  cvId?: string;
};

const NOT_CONFIGURED: CvFormState = {
  error: "Chưa cấu hình Supabase (thiếu NEXT_PUBLIC_SUPABASE_URL / PUBLISHABLE_KEY).",
};

const PROFILE_PATH = "/ho-so";

/**
 * Tải CV kèm consent (S3-T02, US-11).
 * Form gửi: file, consent=on, terms_version (phiên bản điều khoản người dùng đã đọc,
 * lấy từ api.v_cv_terms_current lúc render form).
 * Thứ tự: upload file → api.register_cv (DB ghi consent_at). Ghi DB lỗi thì xóa file vừa upload.
 */
export async function uploadCvAction(_prev: CvFormState, formData: FormData): Promise<CvFormState> {
  if (!isSupabaseConfigured) return NOT_CONFIGURED;

  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Chọn file CV (PDF hoặc DOCX)." };
  const ext = cvExtension(file.type);
  if (!ext) return { error: "Chỉ nhận file PDF hoặc DOCX." };
  if (file.size > CV_MAX_BYTES) return { error: "File CV tối đa 5 MB." };
  if (formData.get("consent") !== "on") {
    return { error: "Bạn cần đồng ý Điều khoản xử lý CV trước khi tải lên." };
  }
  const termsVersion = formData.get("terms_version")?.toString() ?? "";
  if (!termsVersion) return { error: "Thiếu phiên bản điều khoản. Tải lại trang rồi thử lại." };

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: "Bạn cần đăng nhập để tải CV." };

  const cvId = crypto.randomUUID();
  const path = cvStoragePath(user.id, cvId, ext);
  const bytes = await file.arrayBuffer();
  const sha = await sha256Hex(bytes);

  const storage = supabase.storage.from(CV_BUCKET);
  const upload = await storage.upload(path, bytes, { contentType: file.type, upsert: false });
  if (upload.error) return { error: "Tải file lên thất bại. Thử lại sau." };

  const { error } = await supabase.schema("api").rpc("register_cv", {
    p_id: cvId,
    p_storage_path: path,
    p_file_sha256: sha,
    p_mime: file.type,
    p_size_bytes: file.size,
    p_consent_version: termsVersion,
  });
  if (error) {
    // Không để file mồ côi khi DB từ chối
    await storage.remove([path]);
    if (error.code === "23505") return { error: "Bạn đã tải CV này rồi." };
    if (error.code === "23514") return { error: error.message };
    return { error: "Không lưu được CV. Thử lại sau." };
  }

  revalidatePath(PROFILE_PATH);
  return { message: "Đã tải CV lên.", cvId };
}

/**
 * Xóa CV (S3-T02, US-11): xóa file trong Storage trước, rồi api.delete_cv xóa dòng app.cvs.
 * FK cascade xóa cv_skills, cv_chunks, kết quả so khớp; trigger dọn cache giải thích.
 * api.delete_cv từ chối nếu file còn trong Storage, nên lỗi ở bước 1 không làm mất dấu file.
 */
export async function deleteCvAction(cvId: string): Promise<CvFormState> {
  if (!isSupabaseConfigured) return NOT_CONFIGURED;
  if (!isUuid(cvId)) return { error: "CV không hợp lệ." };

  const supabase = await createClient();
  const api = supabase.schema("api");

  const { data: cv, error: readError } = await api
    .from("v_my_cvs")
    .select("id, storage_path")
    .eq("id", cvId)
    .maybeSingle();
  if (readError) return { error: "Không đọc được CV. Thử lại sau." };
  if (!cv) return { error: "Không tìm thấy CV." };

  const removed = await supabase.storage.from(CV_BUCKET).remove([cv.storage_path]);
  if (removed.error) return { error: "Không xóa được file CV, CV chưa bị xóa. Thử lại sau." };

  const { data: deleted, error } = await api.rpc("delete_cv", { p_cv_id: cvId });
  if (error) return { error: "Đã xóa file nhưng chưa xóa được dữ liệu CV. Bấm xóa lại để hoàn tất." };
  if (!deleted) return { error: "Không tìm thấy CV." };

  revalidatePath(PROFILE_PATH);
  return { message: "Đã xóa CV và toàn bộ dữ liệu liên quan." };
}
