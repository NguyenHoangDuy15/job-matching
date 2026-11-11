import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

// Mã không hợp lệ, tin không có, hoặc tin đã đóng/hết hạn (api.v_job_detail chỉ trả tin đang mở).
export default function JobNotFound() {
  return (
    <div className="mx-auto grid w-full max-w-4xl justify-items-start gap-3 px-4 py-12">
      <h1 className="text-2xl font-semibold">Tin này không còn tuyển</h1>
      <p className="text-muted-foreground">
        Tin có thể đã hết hạn nộp, bị gỡ khỏi trang gốc, hoặc đường dẫn không đúng.
      </p>
      <Link href="/viec-lam" className={buttonVariants()}>
        Xem việc làm đang tuyển
      </Link>
    </div>
  );
}
