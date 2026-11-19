import { NextResponse, type NextRequest } from "next/server";
import { requireAccess } from "@/lib/auth";
import { CV_BUCKET, isUuid } from "@/lib/cv";
import { CV_SIGNED_URL_TTL, cvDownloadName } from "@/lib/cv-original";
import { createClient } from "@/lib/supabase/server";

// File CV gốc của chính người dùng (S3-H02, US-12): tạo signed URL mới (5 phút) rồi chuyển hướng.
// Mỗi lần mở / bấm nút tạo URL mới, nên trang để lâu vẫn xem và tải được. Không lưu, không log URL.
// Chỉ người tìm việc (middleware + requireAccess). storage_path đọc qua api.v_my_cvs (RLS chỉ cho
// thấy CV của mình), nên cv_id của người khác ra 404; policy cv_files_seeker của Storage chặn thêm lớp nữa.
// ?tai=1: tải về với tên gốc (Content-Disposition: attachment).

const NO_STORE = { "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" };

function text(body: string, status: number) {
  return new NextResponse(body, { status, headers: { ...NO_STORE, "Content-Type": "text/plain; charset=utf-8" } });
}

export async function GET(request: NextRequest, ctx: RouteContext<"/ho-so/[cvId]/tep">) {
  const { cvId } = await ctx.params;
  await requireAccess(`/ho-so/${cvId}/xac-nhan`);
  if (!isUuid(cvId)) return text("Không tìm thấy CV.", 404);

  const supabase = await createClient();
  const cv = await supabase
    .schema("api")
    .from("v_my_cvs")
    .select("storage_path, mime, original_name")
    .eq("id", cvId)
    .maybeSingle<{ storage_path: string; mime: string; original_name: string | null }>();
  if (cv.error) return text("Chưa đọc được CV, hãy thử lại.", 503);
  if (!cv.data) return text("Không tìm thấy CV.", 404);

  const download = request.nextUrl.searchParams.get("tai") === "1";
  const signed = await supabase.storage
    .from(CV_BUCKET)
    .createSignedUrl(
      cv.data.storage_path,
      CV_SIGNED_URL_TTL,
      download ? { download: cvDownloadName(cv.data.original_name, cv.data.mime) } : undefined,
    );
  // File không còn trong Storage cũng ra 404 (Storage trả lỗi "Object not found").
  if (signed.error || !signed.data) return text("Không mở được file CV, hãy thử lại.", 404);

  return NextResponse.redirect(signed.data.signedUrl, { status: 303, headers: NO_STORE });
}
