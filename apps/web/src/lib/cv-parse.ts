// Gọi API đọc CV POST /cv/parse (S3-D05, docs/deploy/cv-api.md) từ trình duyệt bằng JWT người dùng.
// API đọc file trong Storage, che PII, gán kỹ năng rồi ghi app.cvs / app.cv_skills qua RLS.
import { parseErrorMessage } from "@/lib/cv-profile";

// Biến công khai, nhúng lúc build. Chưa đặt (chưa dựng API) thì bỏ qua bước đọc CV.
export const CV_API_URL = (process.env.NEXT_PUBLIC_CV_API_URL ?? "").replace(/\/+$/, "");
export const isCvApiConfigured = CV_API_URL !== "";

export type ParseResult = { ok: true; skillsSaved: number } | { ok: false; message: string };

export async function parseCv(cvId: string, accessToken: string): Promise<ParseResult> {
  let res: Response;
  try {
    res = await fetch(`${CV_API_URL}/cv/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ cv_id: cvId }),
    });
  } catch {
    return { ok: false, message: parseErrorMessage(0, null) };
  }
  const body = (await res.json().catch(() => null)) as
    | { skills_saved?: number; error?: string; message_vi?: string }
    | null;
  if (!res.ok) return { ok: false, message: parseErrorMessage(res.status, body) };
  return { ok: true, skillsSaved: body?.skills_saved ?? 0 };
}
