// Nơi trang Việc phù hợp lấy kết quả. S4-H01: luôn dùng dữ liệu giả (lib/match-mock.ts).
// S4-H04 sẽ đổi sang gọi POST ${NEXT_PUBLIC_CV_API_URL}/match/jobs bằng JWT (giống lib/cv-parse.ts),
// thêm timeout và thông báo lỗi theo bảng lỗi trong docs/api/match-jobs.md; trang không phải sửa.
import type { MatchRequest, MatchResponse } from "./match.ts";
import { mockMatchJobs } from "./match-mock.ts";

export type MatchOutcome =
  | { ok: true; data: MatchResponse; source: "mock" | "api" }
  | { ok: false; message: string };

const MOCK_DELAY_MS = 600; // để thấy trạng thái đang chấm như khi gọi API thật

export async function fetchMatches(req: MatchRequest, signal?: AbortSignal): Promise<MatchOutcome> {
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, MOCK_DELAY_MS);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    });
  });
  return { ok: true, data: mockMatchJobs(req), source: "mock" };
}
