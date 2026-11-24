// Chạy: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  byLevel,
  DEFAULT_TOP_N,
  displayWeights,
  formulaText,
  matchedLabel,
  numberVi,
  matchableCvs,
  matchHref,
  parseMatchParams,
  pickCv,
  scoreOf,
  toMatchRequest,
  weightsFor,
} from "./match.ts";
import { MOCK_CORPUS_SIZE, mockMatchJobs } from "./match-mock.ts";

const CV = "2f0c1d2e-3a4b-4c5d-8e9f-0a1b2c3d4e5f";

test("đọc URL: giá trị lạ bị bỏ qua, mặc định N = 10", () => {
  assert.deepEqual(parseMatchParams({}), { cvId: null, topN: DEFAULT_TOP_N, provinces: [], modes: [] });
  assert.deepEqual(
    parseMatchParams({ cv: CV.toUpperCase(), n: "20", tinh: "79,1,999,abc,1", "hinh-thuc": ["remote", "onsite,lai"] }),
    { cvId: CV, topN: 20, provinces: [1, 79], modes: ["onsite", "remote"] },
  );
  assert.equal(parseMatchParams({ n: "7" }).topN, 10);
  assert.equal(parseMatchParams({ cv: "khong-phai-uuid" }).cvId, null);
});

test("ghi URL: bỏ giá trị mặc định, đọc lại ra đúng lựa chọn", () => {
  assert.equal(matchHref({ cvId: null, topN: 10, provinces: [], modes: [] }), "/viec-phu-hop");
  const p = { cvId: CV, topN: 50 as const, provinces: [79, 1], modes: ["remote" as const, "onsite" as const] };
  const href = matchHref(p);
  assert.equal(href, `/viec-phu-hop?cv=${CV}&n=50&tinh=1,79&hinh-thuc=onsite,remote`);
  const query = Object.fromEntries(new URLSearchParams(href.split("?")[1]));
  assert.deepEqual(parseMatchParams(query), { ...p, provinces: [1, 79], modes: ["onsite", "remote"] });
  assert.deepEqual(toMatchRequest(p, CV), { cv_id: CV, top_n: 50, filters: { provinces: [79, 1], work_modes: ["remote", "onsite"] } });
});

test("chọn CV: chỉ CV đã đọc xong, CV trên URL trước, rồi CV chính, rồi mới nhất", () => {
  const cvs = [
    { id: "a", is_primary: false, created_at: "2026-11-20T00:00:00Z", parse_status: "parsed" },
    { id: "b", is_primary: true, created_at: "2026-11-10T00:00:00Z", parse_status: "parsed" },
    { id: "c", is_primary: false, created_at: "2026-11-22T00:00:00Z", parse_status: "failed" },
    { id: "d", is_primary: false, created_at: "2026-11-21T00:00:00Z", parse_status: "parsed" },
  ];
  const ok = matchableCvs(cvs);
  assert.deepEqual(ok.map((c) => c.id), ["b", "d", "a"]);
  assert.equal(pickCv(ok, "a")?.id, "a");
  assert.equal(pickCv(ok, "c")?.id, "b"); // CV lỗi phân tích không chấm được
  assert.equal(pickCv(ok, null)?.id, "b");
  assert.equal(pickCv(matchableCvs(cvs.filter((c) => !c.is_primary)), null)?.id, "d");
  assert.equal(pickCv([], CV), null);
});

test("điểm H: chia lại trọng số khi có thành phần null", () => {
  assert.equal(scoreOf({ K: 0.9, M: 0.8, E: 0.85, X: 1 }), 86);
  assert.equal(scoreOf({ K: 0.7, M: 0.6, E: 0.8, X: null }), 69.4);
  const w = weightsFor({ K: 0.7, M: 0.6, E: 0.8, X: null });
  assert.equal(w.X, undefined);
  assert.ok(Math.abs((w.K ?? 0) + (w.M ?? 0) + (w.E ?? 0) - 1) < 1e-9);
  assert.equal(scoreOf({ K: null, M: null, E: null, X: null }), 0);
});

test("mock theo contract: lọc tỉnh (remote / không ghi tỉnh luôn qua), lọc hình thức, sắp điểm, cắt top_n", () => {
  const today = new Date("2026-11-23T00:00:00Z");
  const all = mockMatchJobs({ cv_id: CV, top_n: 50, filters: { provinces: [], work_modes: [] } }, today);
  assert.equal(all.corpus_size, MOCK_CORPUS_SIZE);
  assert.equal(all.results.length, all.candidates);
  assert.deepEqual(all.results.map((r) => r.rank), all.results.map((_, i) => i + 1));
  assert.ok(all.results.every((r, i) => i === 0 || all.results[i - 1].score >= r.score));
  assert.match(all.note, /không phải xác suất trúng tuyển/);
  assert.equal(all.results[0].score, 86);
  assert.equal(all.results[0].valid_through, "2026-12-14");

  const top5 = mockMatchJobs({ cv_id: CV, top_n: 5, filters: { provinces: [], work_modes: [] } }, today);
  assert.equal(top5.results.length, 5);

  const danang = mockMatchJobs({ cv_id: CV, top_n: 50, filters: { provinces: [48], work_modes: [] } }, today);
  assert.ok(danang.results.length > 0);
  assert.ok(danang.results.every((r) => r.provinces.includes("Đà Nẵng") || r.work_mode === "remote" || r.provinces.length === 0));

  const remote = mockMatchJobs({ cv_id: CV, top_n: 50, filters: { provinces: [], work_modes: ["remote"] } }, today);
  assert.ok(remote.results.length > 0);
  assert.ok(remote.results.every((r) => r.work_mode === "remote"));

  const none = mockMatchJobs({ cv_id: CV, top_n: 10, filters: { provinces: [24], work_modes: ["hybrid"] } }, today);
  assert.equal(none.results.length, 0);
});

test("thẻ kết quả: công thức, trọng số, tên chip kỹ năng, bắt buộc trước", () => {
  assert.equal(numberVi(0.9, 2), "0,90");
  assert.equal(numberVi(86, 1), "86,0");

  const withX = { components: { K: 0.9, M: 0.8, E: 0.85, X: 1 }, weights_used: { K: 0.25, M: 0.35, E: 0.3, X: 0.1 } };
  assert.equal(formulaText(displayWeights(withX)), "100 × (0,25 × K + 0,35 × M + 0,30 × E + 0,10 × X)");

  const noX = { components: { K: 0.7, M: 0.6, E: 0.8, X: null }, weights_used: { K: 0.2778, M: 0.3889, E: 0.3333 } };
  assert.equal(formulaText(displayWeights(noX)), "100 × (0,28 × K + 0,39 × M + 0,33 × E)");
  // API không gửi weights_used: tự chia lại, bỏ X.
  const w = displayWeights({ components: noX.components, weights_used: {} });
  assert.deepEqual(Object.keys(w), ["K", "M", "E"]);

  assert.equal(matchedLabel({ skill: "Spark", via: "PySpark" }), "Spark (qua PySpark)");
  assert.equal(matchedLabel({ skill: "Python", via: null }), "Python");
  const sorted = byLevel([
    { skill: "Kafka", level: "preferred" as const },
    { skill: "Java", level: "required" as const },
    { skill: "Redis", level: "preferred" as const },
    { skill: "SQL", level: "required" as const },
  ]);
  assert.deepEqual(sorted.map((s) => s.skill), ["Java", "SQL", "Kafka", "Redis"]);
});
