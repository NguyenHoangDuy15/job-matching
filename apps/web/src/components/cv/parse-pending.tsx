"use client";

import { LoaderCircle, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { isCvApiConfigured, parseCv } from "@/lib/cv-parse";
import { createClient } from "@/lib/supabase/client";

// CV chưa đọc xong (queued / parsing / failed): chưa có gì để xác nhận, cho phân tích (lại).
const STATUS_TEXT: Record<string, { title: string; text: string }> = {
  queued: { title: "CV chưa được phân tích", text: "Bấm Phân tích để hệ thống đọc CV và tìm kỹ năng." },
  parsing: { title: "CV đang được phân tích", text: "Thường mất dưới 15 giây. Tải lại trang sau ít phút." },
  failed: { title: "Lần phân tích trước bị lỗi", text: "CV vẫn được giữ trong hồ sơ của bạn. Hãy thử phân tích lại." },
};

export function ParsePending({ cvId, status }: { cvId: string; status: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const info = STATUS_TEXT[status] ?? STATUS_TEXT.queued;

  async function run() {
    setBusy(true);
    setError(null);
    const token = (await createClient().auth.getSession()).data.session?.access_token;
    const result = token
      ? await parseCv(cvId, token)
      : { ok: false as const, message: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại." };
    setBusy(false);
    if (result.ok) router.refresh();
    else setError(result.message);
  }

  return (
    <div className="grid gap-4">
      <Alert variant={status === "failed" ? "destructive" : "default"}>
        <AlertTitle>{info.title}</AlertTitle>
        <AlertDescription>
          {isCvApiConfigured ? info.text : "Dịch vụ đọc CV chưa được cấu hình (NEXT_PUBLIC_CV_API_URL)."}
        </AlertDescription>
      </Alert>
      {error && (
        <Alert variant="destructive">
          <XCircle aria-hidden />
          <AlertTitle>Chưa phân tích được CV</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        {isCvApiConfigured && (
          <Button type="button" onClick={() => void run()} disabled={busy}>
            {busy && <LoaderCircle className="animate-spin" aria-hidden />}
            {busy ? "Đang phân tích…" : status === "queued" ? "Phân tích" : "Phân tích lại"}
          </Button>
        )}
        <Link href="/ho-so" className={buttonVariants({ variant: "ghost" })}>
          Về Hồ sơ của tôi
        </Link>
      </div>
    </div>
  );
}
