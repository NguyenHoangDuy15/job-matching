// Lỗi khi chấm điểm việc phù hợp (S4-H03 · bảng lỗi trong docs/api/match-jobs.md · wireframe_matches màn 3).
// Mỗi lỗi có câu tiếng Việt cho người dùng, cho Thử lại hay không, và link gợi ý nếu cần.

export type MatchErrorCode =
  | "unauthorized"
  | "cv_not_found"
  | "cv_not_parsed"
  | "bad_request"
  | "rate_limited"
  | "supabase_error"
  | "engine_warming"
  | "matcher_not_configured"
  | "timeout"
  | "network"
  | "unknown";

export type MatchError = {
  code: MatchErrorCode;
  title: string;
  message: string;
  /** Có hiện nút Thử lại không. */
  retry: boolean;
  /** Khóa nút Thử lại trong bấy nhiêu giây (429). */
  waitSeconds?: number;
  action?: { href: string; label: string };
};

/** Quá 30 giây chưa có kết quả thì dừng và báo lỗi (S4-H04 dùng khi gọi API thật). */
export const MATCH_TIMEOUT_MS = 30_000;
/** Quá 5 giây vẫn đang chấm thì báo có thể máy chủ đang khởi động. */
export const SLOW_HINT_MS = 5_000;
/** API giới hạn 20 lượt/phút, không gửi Retry-After: đợi trọn 1 phút. */
export const RATE_LIMIT_WAIT_S = 60;

const PROFILE = { href: "/ho-so", label: "Về Hồ sơ CV" };

const ERRORS: Record<MatchErrorCode, Omit<MatchError, "code">> = {
  unauthorized: {
    title: "Phiên đăng nhập đã hết hạn",
    message: "Hãy đăng nhập lại, hệ thống sẽ đưa bạn về đúng trang này.",
    retry: false,
  },
  cv_not_found: {
    title: "Không tìm thấy CV",
    message: "CV này có thể đã bị xóa. Hãy chọn CV khác hoặc tải CV mới.",
    retry: false,
    action: PROFILE,
  },
  cv_not_parsed: {
    title: "CV chưa đọc xong",
    message: "Hệ thống đang đọc CV này, hãy đợi một lát rồi thử lại.",
    retry: true,
    action: PROFILE,
  },
  bad_request: {
    title: "Lựa chọn không hợp lệ",
    message: "Số việc hoặc bộ lọc gửi lên không đúng. Hãy đặt lại bộ lọc rồi tìm lại.",
    retry: false,
    action: { href: "/viec-phu-hop", label: "Đặt lại bộ lọc" },
  },
  rate_limited: {
    title: "Bạn thao tác quá nhanh",
    message: "Mỗi phút chỉ chấm được 20 lượt. Hãy thử lại sau 1 phút.",
    retry: true,
    waitSeconds: RATE_LIMIT_WAIT_S,
  },
  supabase_error: {
    title: "Có lỗi hệ thống",
    message: "Máy chủ chưa đọc được dữ liệu. Hãy thử lại.",
    retry: true,
  },
  engine_warming: {
    title: "Hệ thống đang khởi động",
    message: "Máy chủ chấm điểm vừa bật lại và đang nạp kho tin (khoảng 15 giây). Hãy thử lại sau ít phút.",
    retry: true,
  },
  matcher_not_configured: {
    title: "Tính năng chưa bật",
    message: "Máy chủ này chưa bật chấm điểm việc phù hợp. Hãy báo nhóm phát triển.",
    retry: false,
  },
  timeout: {
    title: "Chấm điểm lâu hơn bình thường",
    message: "Sau 30 giây vẫn chưa có kết quả, có thể máy chủ đang khởi động. Hãy thử lại.",
    retry: true,
  },
  network: {
    title: "Không kết nối được máy chủ",
    message: "Hãy kiểm tra mạng rồi thử lại.",
    retry: true,
  },
  unknown: {
    title: "Chưa lấy được việc phù hợp",
    message: "Có lỗi không xác định. Hãy thử lại.",
    retry: true,
  },
};

export function matchError(code: MatchErrorCode): MatchError {
  return { code, ...ERRORS[code] };
}

/** Đọc lỗi từ response của POST /match/jobs: body dạng {"error": "..."} (src/api/main.py). */
export function matchErrorFromHttp(status: number, body: unknown): MatchError {
  const code = body && typeof body === "object" && "error" in body ? String(body.error) : "";
  if (status === 401) return matchError("unauthorized");
  if (status === 404) return matchError("cv_not_found");
  if (status === 409) return matchError("cv_not_parsed");
  if (status === 422) return matchError("bad_request");
  if (status === 429) return matchError("rate_limited");
  if (status === 503) return matchError(code === "matcher_not_configured" ? "matcher_not_configured" : "engine_warming");
  if (status === 502) return matchError("supabase_error");
  return matchError("unknown");
}

/**
 * Trang đăng nhập rồi quay lại đúng trang hiện tại, giữ lựa chọn trên URL.
 * Bỏ `gia-lap`: nếu giữ, quay lại sẽ lại giả lập 401 và chuyển đăng nhập mãi.
 */
export function loginHref(pathname: string, search = ""): string {
  const q = new URLSearchParams(search);
  q.delete("gia-lap");
  const rest = q.toString().replace(/%2C/gi, ",");
  return `/dang-nhap?next=${encodeURIComponent(rest ? `${pathname}?${rest}` : pathname)}`;
}

// ---- Giả lập (chỉ khi đang dùng dữ liệu mẫu) ----
// /viec-phu-hop?gia-lap=503 : lần gọi đầu trả lỗi, bấm Thử lại thì có kết quả.

export const SIMULATIONS = {
  "401": "unauthorized",
  "404": "cv_not_found",
  "409": "cv_not_parsed",
  "422": "bad_request",
  "429": "rate_limited",
  "502": "supabase_error",
  "503": "engine_warming",
  tat: "matcher_not_configured",
  "het-gio": "timeout",
  "mat-mang": "network",
  cham: "slow", // chấm lâu 7 giây rồi mới có kết quả, để thấy câu "đang khởi động"
} as const satisfies Record<string, MatchErrorCode | "slow">;

export type Simulation = (typeof SIMULATIONS)[keyof typeof SIMULATIONS];

export function parseSimulation(value: string | string[] | undefined): Simulation | null {
  const v = Array.isArray(value) ? value[0] : value;
  return v && Object.hasOwn(SIMULATIONS, v) ? SIMULATIONS[v as keyof typeof SIMULATIONS] : null;
}
