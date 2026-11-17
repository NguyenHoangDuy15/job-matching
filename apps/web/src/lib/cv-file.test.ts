// Chạy: npm test (node --test, Node ≥ 22.18 tự bỏ kiểu TypeScript).
import assert from "node:assert/strict";
import { test } from "node:test";
import { CV_MAX_BYTES } from "./cv.ts";
import { checkCvFile, formatBytes, registerErrorMessage, uploadErrorMessage } from "./cv-file.ts";

const PDF = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37]);
const ZIP = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x14, 0x00, 0x06, 0x00]);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const OLE = new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]);

const file = (name: string, size = 120_000) => ({ name, size });
const errorOf = (r: ReturnType<typeof checkCvFile>) => (r.ok ? null : r.error);

test("nhận PDF và DOCX đúng nội dung", () => {
  assert.deepEqual(checkCvFile(file("CV.pdf"), PDF), { ok: true, kind: "pdf", mime: "application/pdf" });
  const docx = checkCvFile(file("CV Nguyễn Văn A.DOCX"), ZIP);
  assert.equal(docx.ok && docx.kind, "docx");
});

test("từ chối sai định dạng theo đuôi tệp", () => {
  for (const name of ["anh.png", "cv.txt", "cv", "cv.pdf.exe", "cv.zip"]) {
    assert.equal(errorOf(checkCvFile(file(name), PDF)), "Chỉ nhận PDF hoặc DOCX.", name);
  }
});

test("nhận PDF có dòng trống hoặc byte rác trước %PDF- (trong 1024 byte đầu)", () => {
  const withNewline = new Uint8Array([0x0a, ...PDF]);
  assert.equal(checkCvFile(file("CV.pdf"), withNewline).ok, true);
  const late = new Uint8Array(1100);
  late.set(PDF.subarray(0, 5), 1020);
  assert.equal(checkCvFile(file("CV.pdf"), late).ok, false, "%PDF- không trọn trong 1024 byte đầu");
  late.set(PDF.subarray(0, 5), 500);
  assert.equal(checkCvFile(file("CV.pdf"), late).ok, true);
});

test("từ chối tệp đổi đuôi (nội dung không khớp)", () => {
  assert.match(errorOf(checkCvFile(file("anh-doi-duoi.pdf"), PNG)) ?? "", /không phải PDF/);
  assert.equal(checkCvFile(file("zip.pdf"), ZIP).ok, false);
  assert.equal(checkCvFile(file("pdf.docx"), PDF).ok, false);
});

test("từ chối .doc đời cũ, kể cả khi đổi đuôi thành .docx", () => {
  assert.match(errorOf(checkCvFile(file("cv.doc"), OLE)) ?? "", /\.doc đời cũ/);
  assert.match(errorOf(checkCvFile(file("cv.docx"), OLE)) ?? "", /\.doc đời cũ/);
});

test("giới hạn dung lượng 5 MB và tệp rỗng", () => {
  assert.equal(checkCvFile(file("cv.pdf", CV_MAX_BYTES), PDF).ok, true);
  assert.equal(errorOf(checkCvFile(file("cv.pdf", CV_MAX_BYTES + 1), PDF)), "Tệp quá lớn (tối đa 5 MB).");
  assert.equal(errorOf(checkCvFile(file("cv.pdf", 0), new Uint8Array())), "Tệp rỗng, hãy chọn tệp khác.");
});

test("định dạng dung lượng", () => {
  assert.equal(formatBytes(1_258_291), "1,2 MB");
  assert.equal(formatBytes(120_000), "117 KB");
  assert.equal(formatBytes(10), "1 KB");
});

test("dịch lỗi api.register_cv và Storage", () => {
  assert.equal(registerErrorMessage({ code: "23505" }), "CV này bạn đã tải trước đó.");
  const retired = "Điều khoản phiên bản cv-2026-11 không còn hiệu lực, tải lại trang rồi đồng ý lại";
  assert.equal(registerErrorMessage({ code: "23514", message: retired }), retired);
  assert.equal(
    registerErrorMessage({ code: "23514", message: 'new row violates check constraint "cvs_mime_check"' }),
    "Chưa lưu được CV, hãy thử lại.",
  );
  assert.match(registerErrorMessage({ code: "42501" }), /hết hạn/);
  assert.match(registerErrorMessage({ code: "53400" }), /đã có 5 CV/);
  assert.equal(uploadErrorMessage(413), "Tệp quá lớn (tối đa 5 MB).");
  assert.match(uploadErrorMessage(0), /Mất kết nối/);
});
