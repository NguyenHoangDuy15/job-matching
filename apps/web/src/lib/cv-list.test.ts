// Chạy: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  countSkills,
  cvLabel,
  cvStatus,
  formatDay,
  parseErrorLabel,
  profileLine,
  setPrimaryErrorMessage,
  sortCvs,
} from "./cv-list.ts";

test("trạng thái CV theo parse_status và lần lưu hồ sơ", () => {
  assert.equal(cvStatus({ parse_status: "parsed", profile_confirmed_at: "2026-11-18T03:00:00Z" }), "confirmed");
  assert.equal(cvStatus({ parse_status: "parsed", profile_confirmed_at: null }), "unconfirmed");
  assert.equal(cvStatus({ parse_status: "parsing", profile_confirmed_at: null }), "parsing");
  assert.equal(cvStatus({ parse_status: "failed", profile_confirmed_at: null }), "failed");
  assert.equal(cvStatus({ parse_status: "queued", profile_confirmed_at: null }), "queued");
});

test("đếm kỹ năng theo mức bằng chứng cho từng CV", () => {
  const counts = countSkills([
    { cv_id: "a", evidence_level: "strong" },
    { cv_id: "a", evidence_level: "strong" },
    { cv_id: "a", evidence_level: "listed" },
    { cv_id: "b", evidence_level: "user_added" },
  ]);
  assert.deepEqual(counts.get("a"), { strong: 2, listed: 1, user_added: 0 });
  assert.deepEqual(counts.get("b"), { strong: 0, listed: 0, user_added: 1 });
  assert.equal(counts.get("c"), undefined);
});

test("CV chính đứng đầu, còn lại mới nhất trước", () => {
  const sorted = sortCvs([
    { id: "old", is_primary: false, created_at: "2026-11-10T00:00:00Z" },
    { id: "main", is_primary: true, created_at: "2026-11-01T00:00:00Z" },
    { id: "new", is_primary: false, created_at: "2026-11-17T00:00:00Z" },
  ]);
  assert.deepEqual(sorted.map((r) => r.id), ["main", "new", "old"]);
});

test("tên CV, dòng hồ sơ và ngày", () => {
  assert.equal(cvLabel({ original_name: "CV_Backend.pdf", mime: "application/pdf" }), "CV_Backend.pdf");
  assert.equal(cvLabel({ original_name: null, mime: "application/pdf" }), "CV PDF");
  assert.equal(cvLabel({ original_name: null, mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }), "CV DOCX");
  assert.equal(profileLine({ target_title: "Backend Developer", years_exp: "1.5" }), "Backend Developer · 1,5 năm");
  assert.equal(profileLine({ target_title: "  ", years_exp: 0 }), "0 năm");
  assert.equal(profileLine({ target_title: null, years_exp: null }), null);
  assert.equal(formatDay("2026-12-18"), "18/12/2026");
  assert.equal(formatDay(null), null);
});

test("dịch lỗi phân tích và lỗi đặt CV chính", () => {
  assert.match(parseErrorLabel("ocr_required"), /ảnh chụp/);
  assert.match(parseErrorLabel("encrypted"), /mật khẩu/);
  assert.match(parseErrorLabel(null), /thử phân tích lại/);
  assert.match(setPrimaryErrorMessage({ code: "P0002" }), /Không tìm thấy CV/);
  assert.equal(setPrimaryErrorMessage({ code: "XX000" }), "Chưa đặt được CV chính, hãy thử lại.");
});
