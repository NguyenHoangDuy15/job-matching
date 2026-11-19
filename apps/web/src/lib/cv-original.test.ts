// Chạy: npm test (node --test, Node ≥ 22.18 tự bỏ kiểu TypeScript).
import assert from "node:assert/strict";
import { test } from "node:test";
import { CV_TYPES } from "./cv-file.ts";
import { cvDownloadName, cvFileHref, CV_SIGNED_URL_TTL } from "./cv-original.ts";

const ID = "0b9f7f3e-2c1a-4f7e-9d61-5d1f0d8a1c22";

test("route file gốc: xem và tải về", () => {
  assert.equal(cvFileHref(ID), `/ho-so/${ID}/tep`);
  assert.equal(cvFileHref(ID, true), `/ho-so/${ID}/tep?tai=1`);
});

test("signed URL sống khoảng 5 phút", () => {
  assert.equal(CV_SIGNED_URL_TTL, 300);
});

test("tên tải về giữ tên gốc, thiếu đuôi thì thêm theo MIME", () => {
  assert.equal(cvDownloadName("CV Nguyễn Văn A.pdf", CV_TYPES.pdf), "CV Nguyễn Văn A.pdf");
  assert.equal(cvDownloadName("cv.PDF", CV_TYPES.pdf), "cv.PDF");
  assert.equal(cvDownloadName("ho-so", CV_TYPES.docx), "ho-so.docx");
  assert.equal(cvDownloadName("ho-so.pdf", CV_TYPES.docx), "ho-so.pdf.docx");
});

test("không có tên gốc thì dùng CV.<đuôi>", () => {
  assert.equal(cvDownloadName(null, CV_TYPES.pdf), "CV.pdf");
  assert.equal(cvDownloadName("   ", CV_TYPES.docx), "CV.docx");
});
