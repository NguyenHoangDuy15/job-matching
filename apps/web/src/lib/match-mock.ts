// Dữ liệu giả cho trang Việc phù hợp (S4-H01) khi chưa nối API thật (S4-H04).
// Trả đúng hình dạng MatchResponse của docs/api/match-jobs.md và làm theo các luật của API:
// lọc tỉnh (tin remote / không ghi tỉnh luôn qua), lọc hình thức, sắp theo điểm, cắt top_n.
import { provinceName } from "./jobs/provinces.ts";
import {
  SCORE_DISCLAIMER,
  scoreOf,
  weightsFor,
  type Components,
  type MatchRequest,
  type MatchResponse,
  type MatchResult,
  type SkillMatched,
  type SkillMissing,
} from "./match.ts";

type MockJob = {
  title: string;
  company: string;
  provinces: number[];
  mode: "onsite" | "hybrid" | "remote" | "unknown";
  daysLeft: number | null;
  c: [number | null, number | null, number | null, number | null]; // K, M, E, X
  req: [string[], string[]]; // kỹ năng bắt buộc: [khớp, chưa thể hiện]
  pref: [string[], string[]]; // kỹ năng ưu tiên: [khớp, chưa thể hiện]
};

// prettier-ignore
const JOBS: MockJob[] = [
  { title: "Lập trình viên Java Backend", company: "Công ty B (mẫu)", provinces: [1], mode: "hybrid", daysLeft: 21, c: [0.9, 0.8, 0.85, 1], req: [["Java", "Spring Boot", "PostgreSQL", "Docker"], []], pref: [["Hibernate"], ["Kafka"]] },
  { title: "Backend Developer (Node.js / Java)", company: "Công ty C (mẫu)", provinces: [79], mode: "remote", daysLeft: 3, c: [0.7, 0.6, 0.8, null], req: [["Java", "REST API"], ["Node.js"]], pref: [[], ["MongoDB"]] },
  { title: "Kỹ sư phần mềm (Fullstack)", company: "Công ty D (mẫu)", provinces: [1], mode: "onsite", daysLeft: 15, c: [0.5, 0.4, 0.72, 0.5], req: [["Java"], ["React", "TypeScript"]], pref: [["Git"], ["AWS"]] },
  { title: "Java Developer (Spring)", company: "Công ty E (mẫu)", provinces: [48], mode: "onsite", daysLeft: 30, c: [0.85, 0.78, 0.81, 1], req: [["Java", "Spring Boot", "MySQL"], []], pref: [["Redis"], ["Microservices"]] },
  { title: "Senior Backend Engineer", company: "Công ty F (mẫu)", provinces: [79], mode: "hybrid", daysLeft: 12, c: [0.75, 0.7, 0.83, 0.3], req: [["Java", "Docker", "PostgreSQL"], ["Kubernetes"]], pref: [[], ["Go"]] },
  { title: "Lập trình viên Backend (Golang / Java)", company: "Công ty G (mẫu)", provinces: [], mode: "remote", daysLeft: 25, c: [0.6, 0.55, 0.7, 1], req: [["Java"], ["Go"]], pref: [["Docker"], []] },
  { title: "Software Engineer – Payment", company: "Công ty H (mẫu)", provinces: [1, 79], mode: "hybrid", daysLeft: 40, c: [0.72, 0.66, 0.77, 0.8], req: [["Java", "Spring Boot"], ["Kafka"]], pref: [["Redis"], []] },
  { title: "Kỹ sư dữ liệu (Data Engineer)", company: "Công ty I (mẫu)", provinces: [1], mode: "onsite", daysLeft: 9, c: [0.4, 0.35, 0.6, 1], req: [["Python"], ["Spark", "Airflow"]], pref: [["PostgreSQL"], []] },
  { title: "Lập trình viên .NET", company: "Công ty K (mẫu)", provinces: [48], mode: "onsite", daysLeft: 18, c: [0.3, 0.25, 0.55, 1], req: [[], ["C#", ".NET"]], pref: [["SQL Server"], []] },
  { title: "DevOps Engineer", company: "Công ty L (mẫu)", provinces: [79], mode: "remote", daysLeft: 7, c: [0.45, 0.5, 0.58, null], req: [["Docker", "Linux"], ["Terraform"]], pref: [["Git"], ["AWS"]] },
  { title: "Lập trình viên Java (Fresher+)", company: "Công ty M (mẫu)", provinces: [1], mode: "onsite", daysLeft: 28, c: [0.8, 0.72, 0.74, 1], req: [["Java", "SQL"], []], pref: [["Spring Boot"], []] },
  { title: "Backend Engineer (Microservices)", company: "Công ty N (mẫu)", provinces: [], mode: "unknown", daysLeft: null, c: [0.68, 0.62, 0.79, null], req: [["Java", "REST API"], ["gRPC"]], pref: [["Redis"], []] },
  { title: "Kỹ sư phần mềm nhúng", company: "Công ty O (mẫu)", provinces: [24], mode: "onsite", daysLeft: 20, c: [0.15, 0.1, 0.4, 1], req: [[], ["C", "C++"]], pref: [["Linux"], []] },
  { title: "Fullstack Developer (Java / Angular)", company: "Công ty P (mẫu)", provinces: [79], mode: "hybrid", daysLeft: 14, c: [0.62, 0.58, 0.7, 1], req: [["Java", "Spring Boot"], ["Angular"]], pref: [[], ["TypeScript"]] },
  { title: "Tech Lead Backend", company: "Công ty Q (mẫu)", provinces: [1], mode: "hybrid", daysLeft: 35, c: [0.7, 0.68, 0.8, 0], req: [["Java", "PostgreSQL", "Docker"], []], pref: [["Kafka"], ["Kubernetes"]] },
  { title: "QA Automation Engineer", company: "Công ty R (mẫu)", provinces: [48], mode: "remote", daysLeft: 11, c: [0.35, 0.3, 0.5, 1], req: [["Java"], ["Selenium"]], pref: [[], ["Cypress"]] },
  { title: "Lập trình viên PHP / Laravel", company: "Công ty S (mẫu)", provinces: [1], mode: "onsite", daysLeft: 16, c: [0.2, 0.15, 0.45, 1], req: [["MySQL"], ["PHP", "Laravel"]], pref: [[], []] },
  { title: "Mobile Developer (Android / Kotlin)", company: "Công ty T (mẫu)", provinces: [79], mode: "onsite", daysLeft: 22, c: [0.38, 0.3, 0.52, 1], req: [["Java"], ["Kotlin", "Android"]], pref: [[], []] },
  { title: "Kỹ sư Backend (Python / Django)", company: "Công ty U (mẫu)", provinces: [], mode: "remote", daysLeft: 19, c: [0.42, 0.4, 0.62, 1], req: [["PostgreSQL", "REST API"], ["Python", "Django"]], pref: [["Docker"], []] },
  { title: "Solution Architect (Java)", company: "Công ty V (mẫu)", provinces: [1, 48], mode: "hybrid", daysLeft: 45, c: [0.66, 0.6, 0.76, 0], req: [["Java", "Microservices"], ["AWS"]], pref: [[], ["Kafka"]] },
  { title: "Backend Intern → Junior (Java)", company: "Công ty W (mẫu)", provinces: [79], mode: "onsite", daysLeft: 5, c: [0.78, 0.7, 0.68, 1], req: [["Java", "SQL"], []], pref: [["Git"], []] },
  { title: "Lập trình viên ERP (Java)", company: "Công ty X (mẫu)", provinces: [31], mode: "onsite", daysLeft: 27, c: [0.55, 0.5, 0.6, 1], req: [["Java", "Oracle"], []], pref: [[], ["Spring Boot"]] },
];

export const MOCK_CORPUS_SIZE = 1435;
const NOTE = SCORE_DISCLAIMER;

const slug = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

function dateAfter(days: number, from: Date): string {
  const d = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate() + days));
  return d.toISOString().slice(0, 10);
}

function explain(job: MockJob, components: Components): string {
  const [reqHit, reqMiss] = job.req;
  const [prefHit, prefMiss] = job.pref;
  const parts = [`Khớp ${reqHit.length}/${reqHit.length + reqMiss.length} kỹ năng bắt buộc`];
  if (prefHit.length + prefMiss.length) parts.push(`${prefHit.length}/${prefHit.length + prefMiss.length} kỹ năng ưu tiên`);
  const x = components.X;
  parts.push(x == null ? "tin không ghi số năm kinh nghiệm" : x >= 1 ? "đủ số năm tin yêu cầu" : "chưa đủ số năm tin yêu cầu");
  if (components.E != null) parts.push(`nội dung CV gần với tin này hơn ${Math.round(components.E * 100)}% tin đang mở`);
  return parts.join(" · ");
}

function toResult(job: MockJob, index: number, today: Date): Omit<MatchResult, "rank"> {
  const [K, M, E, X] = job.c;
  const components: Components = { K, M, E, X };
  const matched = (names: string[], level: SkillMatched["level"]): SkillMatched[] =>
    names.map((skill) => ({
      skill_id: slug(skill),
      skill,
      level,
      via: skill === "Hibernate" ? "Spring Data JPA" : null,
      relation: skill === "Hibernate" ? "child" : "exact",
      evidence: skill === "Docker" || skill === "Git" ? "listed" : skill === "Redis" ? "user_added" : "strong",
    }));
  const missing = (names: string[], level: SkillMissing["level"]): SkillMissing[] =>
    names.map((skill) => ({ skill_id: slug(skill), skill, level }));
  const jobId = 9000 + index;
  return {
    job_id: jobId,
    public_id: `00000000-0000-4000-8000-${String(jobId).padStart(12, "0")}`,
    title: job.title,
    company: job.company,
    provinces: job.provinces.map(provinceName),
    work_mode: job.mode,
    valid_through: job.daysLeft == null ? null : dateAfter(job.daysLeft, today),
    apply_url: `https://example.com/viec-mau/${jobId}`, // giả: thẻ mẫu tắt link này
    score: scoreOf(components),
    components,
    weights_used: weightsFor(components),
    skills_matched: [...matched(job.req[0], "required"), ...matched(job.pref[0], "preferred")],
    skills_missing: [...missing(job.req[1], "required"), ...missing(job.pref[1], "preferred")],
    explanation: explain(job, components),
  };
}

/** Giống POST /match/jobs nhưng chạy tại chỗ. `today` để test cố định ngày. */
export function mockMatchJobs(req: MatchRequest, today = new Date()): MatchResponse {
  const { provinces, work_modes } = req.filters;
  const candidates = JOBS.map((job, i) => ({ job, i })).filter(({ job }) => {
    // Tin remote và tin không ghi tỉnh luôn qua bộ lọc tỉnh (docs/api/match-jobs.md).
    const provinceOk =
      provinces.length === 0 || job.mode === "remote" || job.provinces.length === 0 || job.provinces.some((p) => provinces.includes(p));
    const modeOk = work_modes.length === 0 || (job.mode !== "unknown" && work_modes.includes(job.mode));
    return provinceOk && modeOk;
  });
  const results = candidates
    .map(({ job, i }) => toResult(job, i, today))
    .sort((a, b) => b.score - a.score || a.job_id - b.job_id)
    .slice(0, req.top_n)
    .map((r, i) => ({ rank: i + 1, ...r }));
  return {
    request_id: null,
    cv_id: req.cv_id,
    top_n: req.top_n,
    engine_version: "mock",
    corpus_size: MOCK_CORPUS_SIZE,
    candidates: candidates.length,
    latency_ms: 420,
    note: NOTE,
    results,
  };
}
