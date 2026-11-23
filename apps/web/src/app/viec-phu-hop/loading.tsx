import { JobListSkeleton } from "@/components/jobs/job-card";

// Lần đầu vào /viec-phu-hop từ trang khác: hiện khung trong lúc server đọc danh sách CV.
export default function Loading() {
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 px-4 py-8">
      <h1 className="text-2xl font-semibold">Việc phù hợp với tôi</h1>
      <div className="h-28 animate-pulse rounded-lg bg-muted/60" />
      <JobListSkeleton />
    </div>
  );
}
