import assert from "node:assert/strict";
import { test } from "node:test";
import { formatDateTimeVN, formatDetails, formatDuration, formatPct, hasError, toNumber } from "./crawl-runs.ts";

test("toNumber đọc được chuỗi numeric của Supabase", () => {
  assert.equal(toNumber("12.5"), 12.5);
  assert.equal(toNumber(3), 3);
  assert.equal(toNumber(null), null);
  assert.equal(toNumber(""), null);
  assert.equal(toNumber("abc"), null);
});

test("formatDuration: null là đang chạy, đổi giây sang phút/giờ", () => {
  assert.equal(formatDuration(null), "Đang chạy");
  assert.equal(formatDuration("42.4"), "42 giây");
  assert.equal(formatDuration(120), "2 phút");
  assert.equal(formatDuration(125), "2 phút 5 giây");
  assert.equal(formatDuration(3720), "1 giờ 2 phút");
});

test("formatDateTimeVN hiển thị theo giờ Việt Nam", () => {
  // 17:30 UTC = 00:30 hôm sau giờ Việt Nam
  assert.equal(formatDateTimeVN("2026-11-22T17:30:00Z"), "23/11/2026 00:30");
  assert.equal(formatDateTimeVN(null), "—");
  assert.equal(formatDateTimeVN("không phải ngày"), "—");
});

test("formatPct đổi tỉ lệ 0–1 sang phần trăm", () => {
  assert.equal(formatPct("0.9350"), "93,5%");
  assert.equal(formatPct(1), "100%");
  assert.equal(formatPct(0), "0%");
  assert.equal(formatPct(null), "—");
});

test("hasError: thất bại, lỗi HTTP, lỗi schema hoặc có mẫu lỗi", () => {
  const ok = { status: "success" as const, http_errors: 0, schema_errors: 0, error_sample: null };
  assert.equal(hasError(ok), false);
  assert.equal(hasError({ ...ok, error_sample: "  " }), false);
  assert.equal(hasError({ ...ok, status: "failed" }), true);
  assert.equal(hasError({ ...ok, status: "partial" }), true);
  assert.equal(hasError({ ...ok, http_errors: 2 }), true);
  assert.equal(hasError({ ...ok, schema_errors: 1 }), true);
  assert.equal(hasError({ ...ok, error_sample: "HTTP 503" }), true);
  assert.equal(hasError({ ...ok, status: "running", http_errors: null, schema_errors: null }), false);
});

test("formatDetails bỏ qua jsonb rỗng", () => {
  assert.equal(formatDetails(null), null);
  assert.equal(formatDetails({}), null);
  assert.equal(formatDetails({ missing_title: 2 }), '{\n  "missing_title": 2\n}');
});
