// Khung xám lúc đang tải trang chi tiết (thay cho skeleton danh sách của /viec-lam/loading.tsx).
export default function Loading() {
  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6" aria-busy="true" aria-label="Đang tải tin tuyển dụng">
      <div className="h-4 w-36 animate-pulse rounded bg-muted" />
      <div className="grid gap-4 rounded-lg border p-5">
        <div className="h-7 w-3/4 animate-pulse rounded bg-muted" />
        <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
        <div className="h-10 w-64 animate-pulse rounded bg-muted" />
      </div>
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="grid gap-2">
          <div className="h-5 w-40 animate-pulse rounded bg-muted" />
          <div className="h-3 w-full animate-pulse rounded bg-muted" />
          <div className="h-3 w-11/12 animate-pulse rounded bg-muted" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}
