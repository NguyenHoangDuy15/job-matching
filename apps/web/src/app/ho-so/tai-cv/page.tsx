import type { Metadata } from "next";
import { CvUploadForm, type CvTerms } from "@/components/cv/cv-upload-form";
import { PageShell } from "@/components/home-cards";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { requireAccess } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Tải CV" };

// S3-H01 · US-11 · docs/ui/wireframe_cv.png (màn 1, 2). Chỉ người tìm việc (proxy chặn vai trò khác).
// Dữ liệu từ migration 0008 (S3-T02): api.v_cv_terms_current, api.v_my_cvs, api.register_cv.
export default async function UploadCvPage() {
  const session = await requireAccess("/ho-so/tai-cv");

  const api = (await createClient()).schema("api");
  const [terms, cvs] = await Promise.all([
    api.from("v_cv_terms_current").select("version, summary").maybeSingle<CvTerms>(),
    api.from("v_my_cvs").select("id", { count: "exact", head: true }),
  ]);
  const termsData = terms.data;

  return (
    <PageShell title="Tải CV để nhận việc phù hợp">
      <div className="grid max-w-2xl gap-4">
        {!termsData || terms.error || cvs.error ? (
          <Alert variant="destructive">
            <AlertTitle>Chức năng tải CV chưa sẵn sàng</AlertTitle>
            <AlertDescription>
              {terms.error?.code === "PGRST205" || cvs.error?.code === "PGRST205"
                ? "Database chưa có migration 0008 (S3-T02). Báo nhóm chạy migration rồi tải lại trang."
                : !termsData && !terms.error
                  ? "Chưa có Điều khoản xử lý CV đang hiệu lực (ref.cv_terms). Báo nhóm thêm điều khoản."
                  : "Chưa đọc được dữ liệu CV của bạn, hãy tải lại trang."}
            </AlertDescription>
          </Alert>
        ) : (
          <CvUploadForm userId={session.userId} cvCount={cvs.count ?? 0} terms={termsData} />
        )}
      </div>
    </PageShell>
  );
}
