// Nơi trang Việc phù hợp lấy kết quả. Hiện luôn dùng dữ liệu giả (lib/match-mock.ts).
// S4-H04 sẽ đổi sang gọi POST ${NEXT_PUBLIC_CV_API_URL}/match/jobs bằng JWT (giống lib/cv-parse.ts),
// dừng sau MATCH_TIMEOUT_MS và đổi lỗi bằng matchErrorFromHttp (lib/match-errors.ts); trang không phải sửa.
import type { MatchRequest, MatchResponse } from "./match.ts";
import { matchError, type MatchError, type Simulation } from "./match-errors.ts";
import { mockMatchJobs } from "./match-mock.ts";

export type MatchOutcome =
  | { ok: true; data: MatchResponse; source: "mock" | "api" }
  | { ok: false; error: MatchError };

const MOCK_DELAY_MS = 600; // để thấy trạng thái đang chấm như khi gọi API thật
const MOCK_SLOW_MS = 7_000; // giả lập "cham": quá SLOW_HINT_MS để hiện câu đang khởi động

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    });
  });
}

/**
 * `simulate` (S4-H03): giả lập một lỗi trong bảng lỗi của API, chỉ áp dụng với dữ liệu mẫu.
 * Trang chỉ truyền ở lần gọi đầu, nên bấm Thử lại sẽ ra kết quả.
 */
export async function fetchMatches(
  req: MatchRequest,
  { signal, simulate }: { signal?: AbortSignal; simulate?: Simulation | null } = {},
): Promise<MatchOutcome> {
  await wait(simulate === "slow" ? MOCK_SLOW_MS : MOCK_DELAY_MS, signal);
  if (simulate && simulate !== "slow") return { ok: false, error: matchError(simulate) };
  return { ok: true, data: mockMatchJobs(req), source: "mock" };
}
