"use client";

import { CheckCircle2, LoaderCircle, Star, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { deleteCvAction } from "@/app/actions/cv";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  cvLabel,
  cvStatus,
  formatDay,
  parseErrorLabel,
  profileLine,
  setPrimaryErrorMessage,
  STATUS_LABEL,
  type CvListRow,
  type CvStatus,
  type SkillCounts,
} from "@/lib/cv-list";
import { isCvApiConfigured, parseCv } from "@/lib/cv-parse";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

// S3-H04 · US-13 · docs/ui/wireframe_cv.png (màn 4). Mỗi CV: trạng thái, số kỹ năng theo mức,
// hạn lưu; thao tác Sửa / Xác nhận / Phân tích lại, Đặt làm CV chính (api.set_primary_cv),
// Xóa (deleteCvAction của S3-T02: xóa file Storage rồi api.delete_cv, cascade dữ liệu).

const STATUS_STYLE: Record<CvStatus, string> = {
  confirmed: "border-primary bg-primary text-primary-foreground",
  unconfirmed: "border-dashed",
  queued: "text-muted-foreground",
  parsing: "text-muted-foreground",
  failed: "border-destructive text-destructive",
};

type Notice = { kind: "ok" | "error"; title: string; text: string };

export function CvList({ rows, counts }: { rows: CvListRow[]; counts: Record<string, SkillCounts> }) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<CvListRow | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  async function run(id: string, task: () => Promise<Notice | null>) {
    setBusyId(id);
    setNotice(null);
    const result = await task();
    setBusyId(null);
    if (result) setNotice(result);
    router.refresh();
  }

  function setPrimary(row: CvListRow) {
    void run(row.id, async () => {
      const { error } = await createClient().schema("api").rpc("set_primary_cv", { p_cv_id: row.id });
      if (error) return { kind: "error", title: "Chưa đặt được CV chính", text: setPrimaryErrorMessage(error) };
      return { kind: "ok", title: "Đã đổi CV chính", text: `${cvLabel(row)} giờ là CV chính.` };
    });
  }

  function reparse(row: CvListRow) {
    void run(row.id, async () => {
      const token = (await createClient().auth.getSession()).data.session?.access_token;
      if (!token) {
        return { kind: "error", title: "Chưa phân tích được CV", text: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại." };
      }
      const result = await parseCv(row.id, token);
      if (!result.ok) return { kind: "error", title: "Chưa phân tích được CV", text: result.message };
      return { kind: "ok", title: "Đã phân tích xong", text: `${cvLabel(row)}: bấm Xác nhận để kiểm tra kỹ năng.` };
    });
  }

  function askDelete(row: CvListRow) {
    setToDelete(row);
    dialogRef.current?.showModal();
  }

  function confirmDelete() {
    const row = toDelete;
    dialogRef.current?.close();
    if (!row) return;
    void run(row.id, async () => {
      const result = await deleteCvAction(row.id);
      if (result.error) return { kind: "error", title: "Chưa xóa được CV", text: result.error };
      return { kind: "ok", title: "Đã xóa CV", text: `${cvLabel(row)} và mọi kỹ năng đọc từ CV này đã bị xóa.` };
    });
  }

  return (
    <div className="grid gap-4">
      {notice && (
        <Alert variant={notice.kind === "error" ? "destructive" : "default"} aria-live="polite">
          {notice.kind === "error" ? <XCircle aria-hidden /> : <CheckCircle2 aria-hidden />}
          <AlertTitle>{notice.title}</AlertTitle>
          <AlertDescription>{notice.text}</AlertDescription>
        </Alert>
      )}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">CV</th>
              <th scope="col" className="px-3 py-2 font-medium">Trạng thái</th>
              <th scope="col" className="px-3 py-2 font-medium">Kỹ năng</th>
              <th scope="col" className="px-3 py-2 font-medium" title="CV được lưu 30 ngày kể từ lúc tải lên">
                Hạn lưu
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                <span className="sr-only">Thao tác</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const status = cvStatus(row);
              const busy = busyId === row.id;
              const c = counts[row.id];
              const line = profileLine(row);
              const confirmHref = `/ho-so/${row.id}/xac-nhan`;
              return (
                <tr key={row.id} className="border-t align-top" aria-busy={busy || undefined}>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="max-w-64 truncate font-medium" title={cvLabel(row)}>
                        {cvLabel(row)}
                      </span>
                      {row.is_primary && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium">
                          <Star className="size-3 fill-current" aria-hidden /> CV chính
                        </span>
                      )}
                    </div>
                    {line && <div className="text-xs text-muted-foreground">{line}</div>}
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={cn("inline-flex rounded-full border px-2 py-0.5 text-xs whitespace-nowrap", STATUS_STYLE[status])}
                      title={status === "failed" ? parseErrorLabel(row.parse_error) : undefined}
                    >
                      {STATUS_LABEL[status]}
                    </span>
                    {status === "failed" && (
                      <p className="mt-1 max-w-56 text-xs text-muted-foreground">{parseErrorLabel(row.parse_error)}</p>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs whitespace-nowrap">
                    {c && row.parse_status === "parsed" ? (
                      <span title="Có bằng chứng · Chỉ liệt kê · Tự thêm">
                        {c.strong} có bằng chứng · {c.listed} liệt kê · {c.user_added} tự thêm
                      </span>
                    ) : row.parse_status === "parsed" ? (
                      "0 kỹ năng"
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs whitespace-nowrap">{formatDay(row.delete_after) ?? "—"}</td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {busy && <LoaderCircle className="size-4 animate-spin self-center" aria-label="Đang xử lý" />}
                      {status === "confirmed" && (
                        <Link href={confirmHref} className={buttonVariants({ variant: "outline", size: "sm" })}>
                          Sửa
                        </Link>
                      )}
                      {status === "unconfirmed" && (
                        <Link href={confirmHref} className={buttonVariants({ size: "sm" })}>
                          Xác nhận
                        </Link>
                      )}
                      {status !== "confirmed" && status !== "unconfirmed" && isCvApiConfigured && (
                        <Button type="button" size="sm" variant="outline" disabled={busyId !== null} onClick={() => reparse(row)}>
                          {status === "queued" ? "Phân tích" : status === "parsing" ? "Thử lại" : "Phân tích lại"}
                        </Button>
                      )}
                      {!row.is_primary && (
                        <Button type="button" size="sm" variant="ghost" disabled={busyId !== null} onClick={() => setPrimary(row)}>
                          Đặt làm CV chính
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        disabled={busyId !== null}
                        onClick={() => askDelete(row)}
                        aria-label={`Xóa ${cvLabel(row)}`}
                      >
                        Xóa
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground">
        CV chính được dùng mặc định khi chấm Việc phù hợp. Chỉ có 1 CV chính; xóa CV chính thì CV mới nhất còn lại thành
        CV chính.
      </p>

      <dialog
        ref={dialogRef}
        aria-labelledby="delete-cv-title"
        className="m-auto w-[min(28rem,calc(100%-2rem))] rounded-lg border bg-background p-5 text-foreground shadow-lg backdrop:bg-black/40"
        onClose={() => setToDelete(null)}
      >
        <h2 id="delete-cv-title" className="text-lg font-semibold">
          Xóa CV?
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          <b className="text-foreground">{toDelete ? cvLabel(toDelete) : ""}</b> và mọi kỹ năng đọc từ CV này sẽ bị xóa
          vĩnh viễn, không khôi phục được.
          {toDelete?.is_primary && " Đây là CV chính: CV mới nhất còn lại sẽ thành CV chính."}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => dialogRef.current?.close()} autoFocus>
            Hủy
          </Button>
          <Button type="button" variant="destructive" onClick={confirmDelete}>
            Xóa vĩnh viễn
          </Button>
        </div>
      </dialog>
    </div>
  );
}
