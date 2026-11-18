// Hồ sơ kỹ năng của một CV cho màn xác nhận (S3-H02, US-12). Hàm thuần, chạy được cả server lẫn
// trình duyệt và `node --test`. Dữ liệu: app.cv_skills (S3-D05 ghi) + ref.skills (từ điển kỹ năng).

export type EvidenceLevel = "strong" | "listed" | "user_added";

export type CvSkill = {
  skillId: number;
  slug: string;
  name: string;
  level: EvidenceLevel;
  /** Câu trích đã che PII; null với kỹ năng tự thêm. */
  evidence: string | null;
  years: number | null;
  confirmed: boolean;
};

/** Một kỹ năng trong từ điển (ref.skills + ref.skill_aliases) cho ô gợi ý. */
export type TaxonomySkill = { id: number; slug: string; name: string; aliases: string[] };

export const LEVEL_ORDER: EvidenceLevel[] = ["strong", "listed", "user_added"];

export const LEVEL_INFO: Record<EvidenceLevel, { title: string; hint: string }> = {
  strong: { title: "Có bằng chứng", hint: "Kỹ năng xuất hiện trong Kinh nghiệm / Dự án" },
  listed: { title: "Chỉ được liệt kê", hint: "Chỉ có trong mục Kỹ năng, chưa thấy dùng ở đâu" },
  user_added: { title: "Tự thêm", hint: "Bạn thêm, không có trong CV" },
};

/** Chữ thường, bỏ dấu tiếng Việt, gộp ký tự lạ thành dấu cách: "Node.js" → "node js", "Đà" → "da". */
export function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .replace(/[^a-z0-9+#]+/g, " ")
    .trim();
}

/** Sắp theo mức bằng chứng (có bằng chứng → liệt kê → tự thêm), cùng mức thì theo tên. */
export function sortSkills(skills: CvSkill[]): CvSkill[] {
  return [...skills].sort(
    (a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level) || a.name.localeCompare(b.name, "vi"),
  );
}

/**
 * Gợi ý kỹ năng từ từ điển: khớp đầu tên/slug/cách viết khác trước, rồi khớp giữa chuỗi.
 * Gõ không dấu được ("thich nghi" ra "Thích nghi"). Bỏ các kỹ năng đã có trong hồ sơ.
 */
export function searchSkills(
  taxonomy: TaxonomySkill[],
  query: string,
  excludeIds: ReadonlySet<number>,
  limit = 8,
): TaxonomySkill[] {
  const q = normalize(query);
  if (!q) return [];
  const qCompact = q.replace(/ /g, "");
  const scored: { skill: TaxonomySkill; score: number; len: number }[] = [];
  for (const skill of taxonomy) {
    if (excludeIds.has(skill.id)) continue;
    const forms = [skill.name, skill.slug.replace(/_/g, " "), ...skill.aliases].map(normalize);
    // Điểm: 3 = trùng hẳn, 2 = khớp đầu, 1 = khớp giữa. Cùng điểm thì cách viết ngắn hơn đứng trước.
    let score = 0;
    let len = Infinity;
    for (const f of forms) {
      const s = f === q ? 3 : f.startsWith(q) || f.replace(/ /g, "").startsWith(qCompact) ? 2 : f.includes(q) ? 1 : 0;
      if (s > score || (s === score && s > 0 && f.length < len)) {
        score = s;
        len = f.length;
      }
    }
    if (score > 0) scored.push({ skill, score, len });
  }
  return scored
    .sort((a, b) => b.score - a.score || a.len - b.len || a.skill.name.localeCompare(b.skill.name, "vi"))
    .slice(0, limit)
    .map((s) => s.skill);
}

/**
 * Tách câu trích để in đậm tên kỹ năng: [trước, phần khớp, sau]. Không phân biệt hoa thường,
 * thử tên chuẩn rồi tới các cách viết khác (CV ghi "ReactJS", tên chuẩn "React"). null = không thấy.
 */
export function splitEvidence(evidence: string, terms: string[]): [string, string, string] | null {
  const lower = evidence.toLowerCase();
  for (const term of [...terms].sort((a, b) => b.length - a.length)) {
    const t = term.trim().toLowerCase();
    if (t.length < 2) continue;
    let from = 0;
    while (from <= lower.length) {
      const i = lower.indexOf(t, from);
      if (i < 0) break;
      // Chỉ nhận khi đứng riêng thành từ: "Java" không khớp trong "JavaScript".
      const before = i === 0 ? "" : lower[i - 1];
      const after = lower[i + t.length] ?? "";
      if (!/[\p{L}\p{N}]/u.test(before) && !/[\p{L}\p{N}]/u.test(after)) {
        return [evidence.slice(0, i), evidence.slice(i, i + t.length), evidence.slice(i + t.length)];
      }
      from = i + 1;
    }
  }
  return null;
}

/** Thêm kỹ năng người dùng chọn từ từ điển với nhãn "Tự thêm". Đã có thì giữ nguyên. */
export function addUserSkill(skills: CvSkill[], skill: TaxonomySkill): CvSkill[] {
  if (skills.some((s) => s.skillId === skill.id)) return skills;
  return [
    ...skills,
    { skillId: skill.id, slug: skill.slug, name: skill.name, level: "user_added", evidence: null, years: null, confirmed: false },
  ];
}

/** Danh sách cuối cùng gửi cho api.confirm_cv_profile: các kỹ năng người dùng giữ lại. */
export function confirmPayload(skills: CvSkill[]): { skill_id: number }[] {
  return skills.map((s) => ({ skill_id: s.skillId }));
}

/** Có thay đổi so với lúc tải trang không (để hiện "Chưa lưu thay đổi" và hỏi khi rời trang). */
export function hasChanges(initial: CvSkill[], current: CvSkill[]): boolean {
  if (initial.length !== current.length) return true;
  const ids = new Set(initial.map((s) => s.skillId));
  return current.some((s) => !ids.has(s.skillId));
}

/** Lỗi của api.confirm_cv_profile (migration 0010) sang câu cho người dùng. */
export function confirmErrorMessage(err: { code?: string; message?: string }): string {
  if (err.code === "42501") return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại.";
  if (err.code === "P0002") return "Không tìm thấy CV, hãy tải lại trang.";
  if (err.code === "55000") return "CV chưa đọc xong, hãy đợi vài giây rồi tải lại trang.";
  // 22023: dữ liệu sai (số năm ngoài 0–60, kỹ năng không có trong từ điển…), DB viết sẵn tiếng Việt.
  if (err.code === "22023" && err.message) return err.message;
  if (err.code === "PGRST202") return "Chức năng lưu hồ sơ chưa sẵn sàng (thiếu migration). Báo nhóm rồi thử lại.";
  return "Chưa lưu được hồ sơ, hãy thử lại.";
}

/**
 * Lỗi của API đọc CV POST /cv/parse (S3-D05, docs/deploy/cv-api.md) sang câu cho người dùng.
 * Lỗi 422 có message_vi do bộ trích văn bản viết sẵn (CV ảnh chụp, có mật khẩu…).
 */
export function parseErrorMessage(status: number, body: { error?: string; message_vi?: string } | null): string {
  if (status === 401) return "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.";
  if (status === 403) return "Tài khoản đang bị khóa hoặc chờ duyệt.";
  if (status === 404) return "Không tìm thấy CV, hãy tải lại.";
  if (status === 409) return "CV đang được đọc, đợi vài giây rồi tải lại trang.";
  if (status === 422 && body?.message_vi) return body.message_vi;
  if (status === 429) return "Bạn thao tác quá nhanh, thử lại sau 1 phút.";
  if (status === 504) return "File quá phức tạp, hãy xuất lại PDF rồi tải lên.";
  if (status === 0) return "Không kết nối được dịch vụ đọc CV. Hãy kiểm tra mạng rồi thử lại.";
  return "Có lỗi hệ thống khi đọc CV, hãy thử lại.";
}

// --- Số năm kinh nghiệm + chức danh mong muốn (S3-H03) -----------------------------------

export const MAX_YEARS = 60; // api.confirm_cv_profile từ chối ngoài 0–60 (errcode 22023)
export const MAX_TITLE = 200; // app.cvs.target_title cắt 200 ký tự

export type YearsCheck = { ok: true; value: number | null } | { ok: false; error: string };

/**
 * Đọc ô số năm: nhận "1,5" lẫn "1.5", làm tròn 1 chữ số thập phân (như DB).
 * Ô trống = null (giữ nguyên), nhưng chỉ cho trống khi CV chưa có số năm: đã có mà xóa trắng
 * thì báo lỗi, vì gửi null lên sẽ âm thầm giữ số cũ.
 */
export function parseYears(input: string, hadValue: boolean): YearsCheck {
  const text = input.trim().replace(",", ".");
  if (text === "") {
    return hadValue ? { ok: false, error: `Nhập số năm kinh nghiệm từ 0 đến ${MAX_YEARS}.` } : { ok: true, value: null };
  }
  if (!/^\d+(\.\d+)?$/.test(text)) return { ok: false, error: "Số năm kinh nghiệm phải là số, ví dụ 1,5." };
  const value = Math.round(Number(text) * 10) / 10;
  if (value > MAX_YEARS) return { ok: false, error: `Số năm kinh nghiệm từ 0 đến ${MAX_YEARS}.` };
  return { ok: true, value };
}

/** Số năm để hiện trong ô nhập: 1.5 → "1,5"; null → "". */
export function formatYears(value: number | null): string {
  return value == null ? "" : value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

/** Chức danh gửi lên: bỏ khoảng trắng thừa; chuỗi rỗng = xóa chức danh (theo 0010). */
export function cleanTitle(input: string): string {
  return input.replace(/\s+/g, " ").trim().slice(0, MAX_TITLE);
}
