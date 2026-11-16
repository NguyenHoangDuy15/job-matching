"use client";

import { CheckCircle2, Circle, FileText, LoaderCircle, UploadCloud, XCircle } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { CV_BUCKET, cvStoragePath, sha256Hex } from "@/lib/cv";
import { checkCvFile, CV_ACCEPT, formatBytes, MAX_CVS, registerErrorMessage, type CvKind } from "@/lib/cv-file";
import { fileHead, uploadToStorage, UploadError } from "@/lib/cv-upload";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

// S3-H01 · US-11 · docs/ui/wireframe_cv.png (màn 1, 2).
// Thứ tự: kiểm tệp trên trình duyệt → tải lên Storage (có %) → api.register_cv của S3-T02
// (ghi app.cvs + consent theo phiên bản điều khoản). Lưu lỗi thì gỡ tệp vừa tải lên.

export type CvTerms = { version: string; summary: string | null };

type Picked = { file: File; kind: CvKind; mime: string };
type Phase = "idle" | "hashing" | "uploading" | "saving" | "done";

const STEPS: { phase: Exclude<Phase, "idle" | "done">; label: string }[] = [
  { phase: "hashing", label: "Kiểm tra tệp" },
  { phase: "uploading", label: "Tải lên" },
  { phase: "saving", label: "Lưu CV" },
];
const ORDER: Phase[] = ["idle", "hashing", "uploading", "saving", "done"];

export function CvUploadForm({ userId, cvCount, terms }: { userId: string; cvCount: number; terms: CvTerms }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [count, setCount] = useState(cvCount);

  const full = count >= MAX_CVS;
  const busy = phase === "hashing" || phase === "uploading" || phase === "saving";
  const canSubmit = !!picked && consent && !busy && !full && phase !== "done";

  async function pick(file: File | undefined) {
    setError(null);
    setPhase("idle");
    setProgress(0);
    if (!file) return;
    const result = checkCvFile(file, await fileHead(file));
    if (!result.ok) {
      setPicked(null);
      setFileError(result.error);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setFileError(null);
    setPicked({ file, kind: result.kind, mime: result.mime });
  }

  function reset() {
    setPicked(null);
    setFileError(null);
    setError(null);
    setPhase("idle");
    setProgress(0);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!picked || !canSubmit) return;
    const supabase = createClient();
    const api = supabase.schema("api");
    const cvId = crypto.randomUUID();
    const path = cvStoragePath(userId, cvId, picked.kind);
    let uploaded = false;
    setError(null);
    try {
      setPhase("hashing");
      const hash = await sha256Hex(await picked.file.arrayBuffer());

      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token;
      if (!token) throw new UploadError("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại.");

      setPhase("uploading");
      await uploadToStorage({ path, file: picked.file, mime: picked.mime, accessToken: token, onProgress: setProgress });
      uploaded = true;

      setPhase("saving");
      const { error: rpcError } = await api.rpc("register_cv", {
        p_id: cvId,
        p_storage_path: path,
        p_file_sha256: hash,
        p_mime: picked.mime,
        p_size_bytes: picked.file.size,
        p_consent_version: terms.version,
      });
      if (rpcError) throw new UploadError(registerErrorMessage(rpcError));

      setCount((c) => c + 1);
      setPhase("done");
    } catch (err) {
      // Lưu hồ sơ lỗi thì gỡ tệp vừa tải lên để Storage không giữ tệp mồ côi.
      if (uploaded) await supabase.storage.from(CV_BUCKET).remove([path]);
      setError(err instanceof UploadError ? err.message : "Có lỗi khi tải CV, hãy thử lại.");
      setPhase("idle");
      setProgress(0);
    }
  }

  if (phase === "done" && picked) {
    return (
      <div className="grid gap-4">
        <Alert>
          <CheckCircle2 aria-hidden />
          <AlertTitle>Đã lưu CV {picked.file.name}</AlertTitle>
          <AlertDescription>
            Bước phân tích kỹ năng sẽ tự chạy khi dịch vụ đọc CV sẵn sàng (Sprint 3). Bạn đang có {count}/{MAX_CVS} CV.
          </AlertDescription>
        </Alert>
        <Steps phase="done" progress={100} />
        <div className="flex flex-wrap gap-2">
          {count < MAX_CVS && (
            <Button type="button" variant="outline" onClick={reset}>
              Tải CV khác
            </Button>
          )}
          <Link href="/viec-lam" className={buttonVariants({ variant: "ghost" })}>
            Xem việc làm
          </Link>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      {full ? (
        <Alert>
          <AlertTitle>Bạn đã có {MAX_CVS} CV</AlertTitle>
          <AlertDescription>Xóa bớt CV cũ ở trang Hồ sơ của tôi để tải CV mới (Sprint 3).</AlertDescription>
        </Alert>
      ) : (
        <label
          htmlFor="cv-file"
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!busy) void pick(e.dataTransfer.files[0]);
          }}
          className={cn(
            "grid cursor-pointer justify-items-center gap-1 rounded-lg border-2 border-dashed p-8 text-center transition-colors focus-within:ring-3 focus-within:ring-ring/50 hover:bg-muted/50",
            dragging && "border-primary bg-muted",
            busy && "pointer-events-none opacity-60",
          )}
        >
          <UploadCloud className="size-8 text-muted-foreground" aria-hidden />
          <span className="font-medium">
            Kéo thả CV vào đây hoặc <span className="underline underline-offset-4">chọn tệp từ máy</span>
          </span>
          <span className="text-xs text-muted-foreground">
            PDF hoặc DOCX · tối đa 5 MB · PDF phải có chữ chọn được (không phải ảnh chụp)
          </span>
          <input
            ref={inputRef}
            id="cv-file"
            type="file"
            accept={CV_ACCEPT}
            className="sr-only"
            disabled={busy}
            onChange={(e) => void pick(e.target.files?.[0])}
          />
        </label>
      )}

      {fileError && (
        <p role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <XCircle className="size-4 shrink-0" aria-hidden /> {fileError}
        </p>
      )}

      {picked && (
        <div className="flex items-center gap-3 rounded-lg border p-3">
          <FileText className="size-5 shrink-0 text-muted-foreground" aria-hidden />
          <span className="min-w-0 flex-1 truncate font-medium" title={picked.file.name}>
            {picked.file.name}
          </span>
          <span className="text-xs text-muted-foreground">
            {picked.kind.toUpperCase()} · {formatBytes(picked.file.size)}
          </span>
          {!busy && (
            <Button type="button" variant="ghost" size="sm" onClick={reset}>
              Bỏ chọn
            </Button>
          )}
        </div>
      )}

      <fieldset className="grid gap-2 rounded-lg border p-4 text-sm" disabled={busy}>
        <legend className="px-1 font-medium">Đồng ý xử lý CV</legend>
        <p className="text-muted-foreground">
          {terms.summary ?? "Cho phép lưu CV, trích kỹ năng và so khớp với tin tuyển dụng; xóa CV bất kỳ lúc nào."}
        </p>
        <p className="text-xs text-muted-foreground">Điều khoản xử lý CV phiên bản {terms.version}</p>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5 size-4"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>Tôi đã đọc và đồng ý cho hệ thống xử lý CV theo mục đích trên.</span>
        </label>
      </fieldset>

      {error && (
        <Alert variant="destructive">
          <XCircle aria-hidden />
          <AlertTitle>Chưa tải được CV</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {busy && <Steps phase={phase} progress={progress} />}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!canSubmit}>
          {busy && <LoaderCircle className="animate-spin" aria-hidden />}
          {busy ? "Đang tải lên…" : "Tải lên"}
        </Button>
        {!busy && !canSubmit && !full && (
          <span className="text-xs text-muted-foreground">
            {!picked ? "Chọn một tệp PDF hoặc DOCX." : "Tick đồng ý để tải lên."}
          </span>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          Bạn đang có {count}/{MAX_CVS} CV
        </span>
      </div>
    </form>
  );
}

function Steps({ phase, progress }: { phase: Phase; progress: number }) {
  const at = ORDER.indexOf(phase);
  return (
    <div className="grid gap-3 rounded-lg border p-4" aria-live="polite">
      <ol className="grid gap-2 sm:grid-cols-4">
        {STEPS.map((s) => {
          const i = ORDER.indexOf(s.phase);
          const state = at > i ? "done" : at === i ? "now" : "todo";
          return (
            <li
              key={s.phase}
              className={cn(
                "flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm",
                state === "done" && "border-primary bg-primary text-primary-foreground",
                state === "now" && "border-primary font-medium",
                state === "todo" && "text-muted-foreground",
              )}
            >
              {state === "done" ? (
                <CheckCircle2 className="size-4" aria-hidden />
              ) : state === "now" ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : (
                <Circle className="size-4" aria-hidden />
              )}
              {s.label}
              {state === "done" && <span className="sr-only">(xong)</span>}
            </li>
          );
        })}
        <li className="flex items-center gap-2 rounded-md border border-dashed px-2 py-1.5 text-sm text-muted-foreground">
          <Circle className="size-4" aria-hidden /> Phân tích kỹ năng
          <span className="text-xs">(sắp có)</span>
        </li>
      </ol>
      {phase === "uploading" && (
        <div className="grid gap-1">
          <div
            role="progressbar"
            aria-label="Tiến trình tải lên"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
            className="h-2 overflow-hidden rounded-full bg-muted"
          >
            <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
          </div>
          <span className="text-xs text-muted-foreground">Tải lên {progress}%</span>
        </div>
      )}
    </div>
  );
}
