"use client";

import { Star } from "lucide-react";
import { useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { saveErrorMessage } from "@/lib/saved-jobs";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

/**
 * Nút ☆ Lưu / ★ Đã lưu (S4-H05 · US-17). Gọi api.save_job / api.unsave_job bằng phiên trên trình duyệt.
 * Đổi trạng thái ngay khi bấm, lỗi thì trả lại như cũ và báo lý do.
 * `onChange`: trang Việc đã lưu dùng để bỏ dòng khỏi danh sách sau khi bỏ lưu.
 */
export function SaveJobButton({
  publicId,
  initialSaved,
  disabled,
  onChange,
  size = "sm",
}: {
  publicId: string;
  initialSaved: boolean;
  disabled?: boolean;
  onChange?: (saved: boolean) => void;
  size?: "sm" | "default";
}) {
  const [saved, setSaved] = useState(initialSaved);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const next = !saved;
    setSaved(next);
    setBusy(true);
    setError(null);
    const { error: rpcError } = await createClient()
      .schema("api")
      .rpc(next ? "save_job" : "unsave_job", { p_job_id: publicId });
    setBusy(false);
    if (rpcError) {
      setSaved(!next);
      setError(saveErrorMessage(rpcError));
      return;
    }
    onChange?.(next);
  }

  return (
    <span className="inline-grid gap-1">
      <button
        type="button"
        onClick={toggle}
        disabled={disabled || busy}
        aria-pressed={saved}
        title={disabled ? "Dữ liệu mẫu" : saved ? "Bỏ lưu việc này" : "Lưu vào Việc đã lưu"}
        className={cn(buttonVariants({ variant: "outline", size }), disabled && "opacity-50")}
      >
        <Star aria-hidden className={cn(saved && "fill-current text-amber-500")} />
        {saved ? "Đã lưu" : "Lưu"}
      </button>
      {error && (
        <span role="alert" className="max-w-48 text-xs text-destructive">
          {error}
        </span>
      )}
    </span>
  );
}
