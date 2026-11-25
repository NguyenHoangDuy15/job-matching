// Chạy: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import { allowedRolesFor } from "./auth-rules.ts";
import {
  bestScore,
  historyFilterText,
  historyHref,
  historyParams,
  latestScores,
  saveErrorMessage,
  type HistoryResult,
} from "./saved-jobs.ts";

const CV = "2f0c1d2e-3a4b-4c5d-8e9f-0a1b2c3d4e5f";
const res = (public_id: string, rank: number, score_h: number): HistoryResult => ({
  rank,
  public_id,
  title: `Tin ${public_id}`,
  company_name: null,
  score_h,
  k: null,
  m: null,
  e: null,
  x: null,
});

test("Việc đã lưu chỉ dành cho người tìm việc", () => {
  assert.deepEqual(allowedRolesFor("/viec-da-luu"), ["seeker"]);
  assert.deepEqual(allowedRolesFor("/viec-phu-hop"), ["seeker"]);
  assert.equal(allowedRolesFor("/viec-lam"), null);
});

test("lỗi lưu việc: dịch theo errcode của api.save_job", () => {
  assert.match(saveErrorMessage({ code: "42501" }), /đăng nhập/);
  assert.match(saveErrorMessage({ code: "P0002" }), /không còn/);
  assert.match(saveErrorMessage(null), /thử lại/);
});

test("lịch sử: đọc lại lựa chọn, bỏ giá trị lạ, Chấm lại mở đúng CV + bộ lọc", () => {
  const row = { cv_id: CV, top_n: 20, filters: { provinces: [79, 1, 999, "x"], work_modes: ["remote", "bay"] } };
  assert.deepEqual(historyParams(row), { cvId: CV, topN: 20, provinces: [79, 1], modes: ["remote"] });
  assert.equal(historyHref(row), `/viec-phu-hop?cv=${CV}&n=20&tinh=1,79&hinh-thuc=remote`);
  assert.equal(historyFilterText(row), "20 việc · TP. Hồ Chí Minh, Hà Nội · Remote");

  const plain = { cv_id: CV, top_n: 7, filters: null };
  assert.equal(historyParams(plain).topN, 10); // top_n lạ → mặc định
  assert.equal(historyFilterText(plain), "10 việc · mọi tỉnh");
  assert.equal(historyHref(plain), `/viec-phu-hop?cv=${CV}`);
});

test("điểm: cao nhất của một lượt, điểm gần nhất của từng tin (lượt mới thắng)", () => {
  assert.equal(bestScore({ results: [] }), null);
  assert.equal(bestScore({ results: [res("a", 1, 86), res("b", 2, 71.5)] }), 86);

  const scores = latestScores([
    { created_at: "2026-11-20T02:30:00Z", results: [res("a", 1, 80), res("b", 2, 70)] },
    { created_at: "2026-11-24T09:00:00Z", results: [res("a", 1, 84.2)] },
  ]);
  assert.equal(scores.get("a"), 84.2);
  assert.equal(scores.get("b"), 70);
  assert.equal(scores.get("c"), undefined);
});
