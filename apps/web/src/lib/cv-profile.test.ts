// Chạy: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  addUserSkill,
  cleanTitle,
  confirmErrorMessage,
  confirmPayload,
  formatYears,
  hasChanges,
  normalize,
  parseErrorMessage,
  parseYears,
  searchSkills,
  sortSkills,
  splitEvidence,
  type CvSkill,
  type TaxonomySkill,
} from "./cv-profile.ts";

const TAXONOMY: TaxonomySkill[] = [
  { id: 1, slug: "kafka", name: "Apache Kafka", aliases: ["kafka", "apache kafka"] },
  { id: 2, slug: "kafka_streams", name: "Kafka Streams", aliases: ["kafka streams"] },
  { id: 3, slug: "nodejs", name: "Node.js", aliases: ["node.js", "nodejs", "node js"] },
  { id: 4, slug: "adaptability", name: "Thích nghi", aliases: ["thich nghi", "adaptability"] },
  { id: 5, slug: "java", name: "Java", aliases: ["java"] },
  { id: 6, slug: "javascript", name: "JavaScript", aliases: ["javascript", "js"] },
  { id: 7, slug: "csharp", name: "C#", aliases: ["c#", "csharp"] },
];

const skill = (skillId: number, name: string, level: CvSkill["level"], evidence: string | null = null): CvSkill => ({
  skillId,
  slug: name.toLowerCase(),
  name,
  level,
  evidence,
  years: null,
  confirmed: false,
});

test("chuẩn hóa: bỏ dấu, chữ thường, giữ + và #", () => {
  assert.equal(normalize("Node.js"), "node js");
  assert.equal(normalize("Thích nghi"), "thich nghi");
  assert.equal(normalize("Đà Nẵng"), "da nang");
  assert.equal(normalize("C++ / C#"), "c++ c#");
});

test("gợi ý kỹ năng: khớp đầu tên trước, gõ không dấu, theo cách viết khác", () => {
  const none = new Set<number>();
  assert.deepEqual(searchSkills(TAXONOMY, "kaf", none).map((s) => s.id), [1, 2]);
  assert.deepEqual(searchSkills(TAXONOMY, "thich", none).map((s) => s.id), [4]);
  assert.deepEqual(searchSkills(TAXONOMY, "nodejs", none).map((s) => s.id), [3]);
  assert.deepEqual(searchSkills(TAXONOMY, "java", none).map((s) => s.id), [5, 6]);
  assert.deepEqual(searchSkills(TAXONOMY, "c#", none).map((s) => s.id), [7]);
  assert.deepEqual(searchSkills(TAXONOMY, "  ", none), []);
  assert.deepEqual(searchSkills(TAXONOMY, "khong co", none), []);
});

test("gợi ý bỏ kỹ năng đã có trong hồ sơ", () => {
  assert.deepEqual(searchSkills(TAXONOMY, "kaf", new Set([1])).map((s) => s.id), [2]);
});

test("in đậm tên kỹ năng trong câu trích, chỉ khớp nguyên từ", () => {
  assert.deepEqual(splitEvidence("Xây REST API bằng Java Spring Boot", ["Java"]), ["Xây REST API bằng ", "Java", " Spring Boot"]);
  assert.equal(splitEvidence("Viết JavaScript cho trang quản trị", ["Java"]), null);
  assert.deepEqual(splitEvidence("Dùng ReactJS và Redux", ["React", "reactjs"]), ["Dùng ", "ReactJS", " và Redux"]);
  assert.deepEqual(splitEvidence("Java, Javascript", ["java"]), ["", "Java", ", Javascript"]);
});

test("thêm kỹ năng tự thêm, không thêm trùng", () => {
  const start = [skill(5, "Java", "strong", "Dùng Java")];
  const added = addUserSkill(start, TAXONOMY[0]);
  assert.equal(added.length, 2);
  assert.deepEqual(added[1], { skillId: 1, slug: "kafka", name: "Apache Kafka", level: "user_added", evidence: null, years: null, confirmed: false });
  assert.equal(addUserSkill(added, TAXONOMY[0]), added);
});

test("sắp theo mức bằng chứng rồi theo tên", () => {
  const sorted = sortSkills([skill(1, "Kafka", "user_added"), skill(2, "React", "listed"), skill(3, "Docker", "strong"), skill(4, "AWS", "listed")]);
  assert.deepEqual(sorted.map((s) => s.name), ["Docker", "AWS", "React", "Kafka"]);
});

test("phát hiện thay đổi và dữ liệu gửi lưu", () => {
  const initial = [skill(1, "A", "strong"), skill(2, "B", "listed")];
  assert.equal(hasChanges(initial, [...initial].reverse()), false);
  assert.equal(hasChanges(initial, initial.slice(1)), true);
  assert.equal(hasChanges(initial, [initial[0], skill(3, "C", "user_added")]), true);
  assert.deepEqual(confirmPayload(initial), [{ skill_id: 1 }, { skill_id: 2 }]);
});

test("dịch lỗi lưu hồ sơ và lỗi API đọc CV", () => {
  assert.match(confirmErrorMessage({ code: "42501" }), /hết hạn/);
  assert.match(confirmErrorMessage({ code: "PGRST202" }), /chưa sẵn sàng/);
  const bad = "Kỹ năng 999 không có trong từ điển";
  assert.equal(confirmErrorMessage({ code: "22023", message: bad }), bad);
  assert.equal(confirmErrorMessage({ code: "XX000" }), "Chưa lưu được hồ sơ, hãy thử lại.");
  const ocr = "CV là ảnh chụp, hãy xuất lại PDF từ Word.";
  assert.equal(parseErrorMessage(422, { error: "ocr_required", message_vi: ocr }), ocr);
  assert.match(parseErrorMessage(409, null), /đang được đọc/);
  assert.match(parseErrorMessage(504, { error: "timeout" }), /quá phức tạp/);
  assert.match(parseErrorMessage(502, { error: "worker_unavailable" }), /lỗi hệ thống/);
  assert.match(parseErrorMessage(0, null), /Không kết nối/);
});

test("đọc số năm kinh nghiệm: dấu phẩy, làm tròn, giới hạn 0–60, ô trống", () => {
  assert.deepEqual(parseYears("1,5", true), { ok: true, value: 1.5 });
  assert.deepEqual(parseYears(" 3.25 ", true), { ok: true, value: 3.3 });
  assert.deepEqual(parseYears("0", true), { ok: true, value: 0 });
  assert.deepEqual(parseYears("60", true), { ok: true, value: 60 });
  assert.equal(parseYears("61", true).ok, false);
  assert.equal(parseYears("-1", true).ok, false);
  assert.equal(parseYears("hai", true).ok, false);
  assert.equal(parseYears("1,5,2", true).ok, false);
  assert.deepEqual(parseYears("", false), { ok: true, value: null });
  assert.match((parseYears("", true) as { error: string }).error, /từ 0 đến 60/);
});

test("hiện số năm và làm sạch chức danh", () => {
  assert.equal(formatYears(1.5), "1,5");
  assert.equal(formatYears(4), "4");
  assert.equal(formatYears(null), "");
  assert.equal(cleanTitle("  Backend   Developer  "), "Backend Developer");
  assert.equal(cleanTitle("   "), "");
  assert.equal(cleanTitle("a".repeat(250)).length, 200);
});
