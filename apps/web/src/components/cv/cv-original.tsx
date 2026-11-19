import { Download, ExternalLink, FileText, Lock } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cvFileHref } from "@/lib/cv-original";
import { cn } from "@/lib/utils";

// S3-H02 · US-12. File CV gốc để đối chiếu với kỹ năng hệ thống đọc được. Không dùng text_redacted
// (có nhãn [HỌ_TÊN]... trông như lỗi). File đi qua route /ho-so/[cvId]/tep (signed URL 5 phút, tạo
// mới mỗi lần mở). PDF xem ngay trong trang; DOCX trình duyệt không xem được nên chỉ cho tải về.

const PRIVACY_NOTE = "Chỉ bạn xem được file này. File bị xóa khi bạn xóa CV.";

function Actions({ cvId, pdf }: { cvId: string; pdf: boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {pdf && (
        <a
          href={cvFileHref(cvId)}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          <ExternalLink aria-hidden />
          Mở trong tab mới
        </a>
      )}
      <a href={cvFileHref(cvId, true)} className={buttonVariants({ variant: "outline", size: "sm" })}>
        <Download aria-hidden />
        Tải về
      </a>
    </div>
  );
}

function Note() {
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Lock className="size-3 shrink-0" aria-hidden />
      {PRIVACY_NOTE}
    </p>
  );
}

export function CvOriginal({
  cvId,
  fileLabel,
  pdf,
  className,
}: {
  cvId: string;
  /** Tên tệp gốc (hoặc "CV PDF") để đặt tiêu đề khung xem. */
  fileLabel: string;
  pdf: boolean;
  className?: string;
}) {
  if (!pdf) {
    return (
      <section aria-label="CV gốc của bạn" className={cn("grid gap-2 rounded-lg border p-4", className)}>
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <FileText className="size-4 shrink-0" aria-hidden />
          CV gốc của bạn
        </h2>
        <p className="text-sm text-muted-foreground">
          Trình duyệt không xem trực tiếp được file DOCX. Tải về rồi mở bằng Word hoặc Google Docs để đối chiếu.
        </p>
        <Actions cvId={cvId} pdf={false} />
        <Note />
      </section>
    );
  }

  return (
    <section aria-label="CV gốc của bạn" className={cn("grid content-start gap-2", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex min-w-0 items-center gap-2 text-sm font-medium">
          <FileText className="size-4 shrink-0" aria-hidden />
          <span className="truncate" title={fileLabel}>
            CV gốc: {fileLabel}
          </span>
        </h2>
        <Actions cvId={cvId} pdf />
      </div>
      {/* <object> thay vì <iframe>: trình duyệt không xem được PDF (Chrome Android) thì hiện nội dung
          bên trong thay vì tự tải file về. */}
      <object
        data={cvFileHref(cvId)}
        type="application/pdf"
        aria-label={`CV gốc: ${fileLabel}`}
        className="h-[70vh] w-full rounded-lg border bg-muted lg:h-[calc(100vh-10rem)]"
      >
        <div className="grid h-full content-center justify-items-center gap-2 p-4 text-center text-sm text-muted-foreground">
          <p>Trình duyệt này không xem PDF ngay trong trang được.</p>
          <p>Bấm “Mở trong tab mới” hoặc “Tải về” ở trên.</p>
        </div>
      </object>
      <Note />
    </section>
  );
}
