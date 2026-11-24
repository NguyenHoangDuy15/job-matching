import assert from "node:assert/strict";
import { test } from "node:test";
import {
  formatFreshness,
  isLowQuality,
  isStale,
  latestReportPerSource,
  type QualityReportRow,
} from "./quality-reports.ts";

function row(source_id: number, source_name: string, started_at: string, completeness = "0.9000"): QualityReportRow {
  return {
    source_id,
    source_code: source_name.toLowerCase(),
    source_name,
    status: "success",
    started_at,
    completeness,
    validity: "1.0000",
    uniqueness: "0.9500",
    salary_parsed_pct: "0.6000",
    province_parsed_pct: "0.9000",
    schema_errors: 0,
    freshness_hours: "34.00",
  };
}

test("latestReportPerSource giữ lần chạy mới nhất của mỗi nguồn, sắp theo tên", () => {
  const rows = [
    row(2, "TopCV", "2026-11-23T03:00:00Z", "0.9100"),
    row(1, "ITviec", "2026-11-23T02:00:00Z"),
    row(2, "TopCV", "2026-11-22T03:00:00Z", "0.5000"),
    row(3, "CareerViet", "2026-11-21T03:00:00Z"),
  ];
  const out = latestReportPerSource(rows);
  assert.deepEqual(
    out.map((r) => r.source_name),
    ["CareerViet", "ITviec", "TopCV"],
  );
  assert.equal(out.find((r) => r.source_id === 2)?.completeness, "0.9100");
  assert.deepEqual(latestReportPerSource([]), []);
});

test("isLowQuality tô đỏ khi tỉ lệ dưới ngưỡng, bỏ qua null", () => {
  assert.equal(isLowQuality("completeness", "0.7999"), true);
  assert.equal(isLowQuality("completeness", "0.8000"), false);
  assert.equal(isLowQuality("validity", 0.9), true);
  assert.equal(isLowQuality("salary_parsed_pct", null), false);
});

test("isStale khi tin mới nhất cũ hơn 48 giờ", () => {
  assert.equal(isStale("48.00"), false);
  assert.equal(isStale("48.5"), true);
  assert.equal(isStale(null), false);
});

test("formatFreshness hiện giờ dưới 48 giờ, từ đó hiện ngày", () => {
  assert.equal(formatFreshness("34.00"), "34 giờ");
  assert.equal(formatFreshness(0), "0 giờ");
  assert.equal(formatFreshness("80"), "3 ngày");
  assert.equal(formatFreshness(null), "—");
});
