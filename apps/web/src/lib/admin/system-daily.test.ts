import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildAlerts,
  buildCrawlSeries,
  buildP95Series,
  formatInt,
  formatMs,
  formatUsd,
  type SourceDailyRow,
  type SystemDailyRow,
  vnDay,
} from "./system-daily.ts";

// 23/11/2026 10:00 giờ Việt Nam
const NOW = new Date("2026-11-23T03:00:00Z");

const LATEST: SystemDailyRow = {
  day: "2026-11-23",
  jobs_open: "1200",
  jobs_new: "40",
  jobs_new_24h: "55",
  jobs_closed: "3",
  users_seeker: "90",
  users_hr: "12",
  users_admin: "2",
  logins_today: "17",
  matches: "300",
  p95_ms: "420",
  crawl_success_pct: "95.0",
  llm_cost_usd: "0.42",
  refreshed_at: "2026-11-23T02:50:00Z",
};

const SOURCE: SourceDailyRow = {
  day: "2026-11-23",
  source_id: 1,
  source_code: "topcv",
  source_name: "TopCV",
  is_enabled: true,
  jobs_open: "800",
  jobs_new_24h: "30",
  refreshed_at: "2026-11-23T02:50:00Z",
};

test("vnDay tính ngày theo giờ Việt Nam", () => {
  // 17:30 UTC = 00:30 hôm sau giờ Việt Nam
  assert.equal(vnDay(new Date("2026-11-22T17:30:00Z")), "2026-11-23");
  assert.equal(vnDay(new Date("2026-11-22T16:59:00Z")), "2026-11-22");
});

test("buildCrawlSeries: 7 điểm kết thúc hôm nay, ngày thiếu là null", () => {
  const series = buildCrawlSeries(
    [
      { day: "2026-11-23", crawl_success_pct: "95.5" },
      { day: "2026-11-20", crawl_success_pct: 70 },
      { day: "2026-11-19", crawl_success_pct: null },
      { day: "2026-11-10", crawl_success_pct: 100 },
    ],
    NOW,
  );
  assert.equal(series.length, 7);
  assert.equal(series[0].day, "2026-11-17");
  assert.equal(series[6].day, "2026-11-23");
  assert.equal(series[6].label, "23/11");
  assert.equal(series[6].pct, 95.5);
  assert.equal(series[3].pct, 70);
  assert.equal(series[2].pct, null);
  assert.equal(series[5].pct, null);
});

test("buildP95Series: 7 điểm, ngày thiếu là null", () => {
  const s = buildP95Series(
    [
      { day: "2026-11-23", p95_ms: "420" },
      { day: "2026-11-21", p95_ms: 1500 },
    ],
    NOW,
  );
  assert.equal(s.length, 7);
  assert.equal(s[0].day, "2026-11-17");
  assert.equal(s[6].ms, 420);
  assert.equal(s[4].ms, 1500);
  assert.equal(s[5].ms, null);
});

test("buildAlerts: không có cảnh báo khi mọi thứ ổn", () => {
  assert.deepEqual(buildAlerts({ latest: LATEST, sources: [SOURCE], failedRuns: [], now: NOW }), []);
});

test("buildAlerts: chưa có số liệu", () => {
  const alerts = buildAlerts({ latest: null, sources: [], failedRuns: [], now: NOW });
  assert.deepEqual(
    alerts.map((a) => a.key),
    ["no-data"],
  );
});

test("buildAlerts: số liệu cũ và tỉ lệ crawl dưới ngưỡng", () => {
  const alerts = buildAlerts({
    latest: { ...LATEST, refreshed_at: "2026-11-23T00:00:00Z", crawl_success_pct: "72.5" },
    sources: [],
    failedRuns: [],
    now: NOW,
  });
  assert.deepEqual(
    alerts.map((a) => a.key),
    ["stale", "crawl-low"],
  );
  assert.match(alerts[0].detail, /3 giờ/);
  assert.equal(alerts[1].detail, "Hôm nay 72,5%, dưới ngưỡng 80%.");
  assert.equal(alerts[1].href, "/admin/crawl-runs");
});

test("buildAlerts: lần crawl thất bại dẫn tới đúng lần chạy, quá 5 lần thì gộp", () => {
  const failedRuns = Array.from({ length: 7 }, (_, i) => ({
    id: 100 + i,
    source_name: "ITviec",
    started_at: "2026-11-23T01:00:00Z",
    error_sample: i === 0 ? "HTTP 503 Service Unavailable\nTraceback ..." : null,
  }));
  const alerts = buildAlerts({ latest: LATEST, sources: [], failedRuns, now: NOW });
  assert.equal(alerts.length, 6);
  assert.equal(alerts[0].title, "Crawl ITviec thất bại");
  assert.equal(alerts[0].detail, "HTTP 503 Service Unavailable");
  assert.equal(alerts[0].href, "/admin/crawl-runs?run=100#run-100");
  assert.equal(alerts[1].detail, "Không có mẫu lỗi.");
  assert.equal(alerts[5].key, "run-more");
  assert.equal(alerts[5].title, "Còn 2 lần thất bại khác trong 24 giờ");
});

test("buildAlerts: nguồn đang bật mà 0 tin mở, nguồn tắt thì bỏ qua", () => {
  const alerts = buildAlerts({
    latest: LATEST,
    sources: [
      { ...SOURCE, source_id: 2, source_name: "TopDev", jobs_open: "0" },
      { ...SOURCE, source_id: 3, source_name: "ITviec", jobs_open: null },
      { ...SOURCE, source_id: 4, source_name: "Cũ", is_enabled: false, jobs_open: 0 },
    ],
    failedRuns: [],
    now: NOW,
  });
  assert.deepEqual(
    alerts.map((a) => a.key),
    ["source-2", "source-3"],
  );
  assert.equal(alerts[0].title, "Nguồn TopDev không còn tin đang mở");
});

test("formatInt, formatUsd, formatMs", () => {
  assert.equal(formatInt("12345"), "12.345");
  assert.equal(formatInt(null), "—");
  assert.equal(formatUsd("0.4"), "$0.40");
  assert.equal(formatUsd(null), "—");
  assert.equal(formatMs("420.4"), "420 ms");
  assert.equal(formatMs(1500), "1,5 giây");
  assert.equal(formatMs(null), "—");
});
