// Nơi trang Việc phù hợp lấy kết quả (S4-H04 · docs/api/match-jobs.md).
// Có NEXT_PUBLIC_CV_API_URL: gọi POST /match/jobs bằng JWT người dùng, dừng sau MATCH_TIMEOUT_MS.
// Chưa đặt biến này (máy dev chưa dựng API): dùng dữ liệu mẫu lib/match-mock.ts như S4-H01.
// Lỗi đổi sang câu tiếng Việt bằng lib/match-errors.ts (S4-H03).
import type { MatchRequest, MatchResponse } from "./match.ts";
import { MATCH_TIMEOUT_MS, matchError, matchErrorFromHttp, type MatchError, type Simulation } from "./match-errors.ts";
import { mockMatchJobs } from "./match-mock.ts";

/** Biến công khai, nhúng lúc build (cùng API đọc CV, xem lib/cv-parse.ts). */
export const MATCH_API_URL = (process.env.NEXT_PUBLIC_CV_API_URL ?? "").replace(/\/+$/, "");

export type MatchOutcome =
  | {
      ok: true;
      data: MatchResponse;
      source: "mock" | "api";
      /** Thời gian người dùng phải chờ, đo ở trình duyệt (gồm mạng, máy chủ thức dậy). */
      elapsedMs: number;
    }
  | { ok: false; error: MatchError };

/** Lấy JWT: `token` đọc phiên hiện tại, `refresh` xin token mới khi API trả 401. */
export type MatchAuth = {
  token: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
};

export type FetchMatchesOptions = {
  signal?: AbortSignal;
  /** Giả lập lỗi (?gia-lap=…, S4-H03). Trang chỉ truyền ở lần gọi đầu nên Thử lại sẽ ra kết quả. */
  simulate?: Simulation | null;
  /** Không có auth hoặc không có URL API thì dùng dữ liệu mẫu. */
  auth?: MatchAuth;
  apiUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
};

const MOCK_DELAY_MS = 600; // để thấy trạng thái đang chấm như khi gọi API thật
const MOCK_SLOW_MS = 7_000; // giả lập "cham": quá SLOW_HINT_MS để hiện câu đang khởi động

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    });
  });
}

export async function fetchMatches(req: MatchRequest, opts: FetchMatchesOptions = {}): Promise<MatchOutcome> {
  const { signal, simulate, auth } = opts;
  const apiUrl = opts.apiUrl ?? MATCH_API_URL;
  const started = Date.now();

  if (simulate && simulate !== "slow") {
    await wait(MOCK_DELAY_MS, signal);
    return { ok: false, error: matchError(simulate) };
  }
  if (simulate === "slow") await wait(MOCK_SLOW_MS, signal);

  if (!apiUrl || !auth) {
    if (simulate !== "slow") await wait(MOCK_DELAY_MS, signal);
    return { ok: true, data: mockMatchJobs(req), source: "mock", elapsedMs: Date.now() - started };
  }

  const outcome = await callMatchApi(req, { ...opts, apiUrl, auth });
  return outcome.ok ? { ...outcome, elapsedMs: Date.now() - started } : outcome;
}

type ApiOptions = FetchMatchesOptions & { apiUrl: string; auth: MatchAuth };

/** POST /match/jobs. 401 thì làm mới phiên rồi gửi lại đúng một lần. Hết giờ / mất mạng đổi thành lỗi. */
async function callMatchApi(req: MatchRequest, opts: ApiOptions): Promise<MatchOutcome> {
  const { signal, auth, apiUrl } = opts;
  const doFetch = opts.fetchImpl ?? fetch;

  // Một bộ hẹn giờ cho cả lượt (kể cả lần gửi lại sau 401). Trang hủy (đổi lựa chọn) thì hủy theo.
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, opts.timeoutMs ?? MATCH_TIMEOUT_MS);
  const onAbort = () => ctrl.abort(signal?.reason);
  signal?.addEventListener("abort", onAbort);
  if (signal?.aborted) onAbort();

  const post = (token: string) => {
    // Có thể đã hủy trong lúc chờ lấy token: dừng luôn, không gửi.
    if (ctrl.signal.aborted) return Promise.reject(ctrl.signal.reason ?? new Error("aborted"));
    return doFetch(`${apiUrl}/match/jobs`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal: ctrl.signal,
    });
  };

  try {
    let token = await auth.token();
    if (!token) return { ok: false, error: matchError("unauthorized") };
    let res = await post(token);
    if (res.status === 401) {
      token = await auth.refresh();
      if (!token) return { ok: false, error: matchError("unauthorized") };
      res = await post(token);
    }

    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) return { ok: false, error: matchErrorFromHttp(res.status, body) };
    if (!isMatchResponse(body)) return { ok: false, error: matchError("unknown") };
    return { ok: true, data: body, source: "api", elapsedMs: 0 };
  } catch (err) {
    if (signal?.aborted) throw err; // trang đã bỏ lượt này, không hiện gì
    return { ok: false, error: matchError(timedOut ? "timeout" : "network") };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

/** Kiểm vừa đủ để không vỡ trang nếu API trả sai dạng (schema đầy đủ: src/api/match.py). */
function isMatchResponse(body: unknown): body is MatchResponse {
  if (!body || typeof body !== "object") return false;
  const b = body as Partial<MatchResponse>;
  return Array.isArray(b.results) && typeof b.corpus_size === "number" && typeof b.latency_ms === "number";
}
