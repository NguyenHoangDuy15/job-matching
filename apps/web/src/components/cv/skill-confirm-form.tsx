"use client";

import { CheckCircle2, LoaderCircle, Plus, Undo2, X, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addUserSkill,
  cleanTitle,
  confirmErrorMessage,
  confirmPayload,
  formatYears,
  hasChanges,
  LEVEL_INFO,
  MAX_TITLE,
  parseYears,
  searchSkills,
  sortSkills,
  splitEvidence,
  type CvSkill,
  type EvidenceLevel,
  type TaxonomySkill,
} from "@/lib/cv-profile";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

// S3-H02, S3-H03 · US-12 · docs/ui/wireframe_cv.png (màn 3). Xác nhận hồ sơ CV: chức danh mong
// muốn + tổng số năm kinh nghiệm (sửa được), kỹ năng theo mức bằng chứng (xem câu trích, xóa kỹ
// năng sai, thêm từ từ điển với nhãn "Tự thêm"). Lưu tất cả một lần bằng api.confirm_cv_profile (0010).

const STRONG_PREVIEW = 5;
const LEAVE_PROMPT = "Bỏ các thay đổi chưa lưu?";

export function SkillConfirmForm({
  cvId,
  initialSkills,
  taxonomy,
  initialYears,
  initialTitle,
  confirmedLabel,
}: {
  cvId: string;
  initialSkills: CvSkill[];
  taxonomy: TaxonomySkill[];
  initialYears: number | null;
  initialTitle: string | null;
  /** Lần lưu gần nhất (profile_confirmed_at, đã định dạng ở server); null = chưa xác nhận. */
  confirmedLabel: string | null;
}) {
  const router = useRouter();
  const fieldId = useId();
  const [savedYears, setSavedYears] = useState(initialYears);
  const [savedTitle, setSavedTitle] = useState(initialTitle ?? "");
  const [yearsText, setYearsText] = useState(() => formatYears(initialYears));
  const [titleText, setTitleText] = useState(initialTitle ?? "");
  const [lastSaved, setLastSaved] = useState(confirmedLabel);
  const [saved, setSaved] = useState(() => sortSkills(initialSkills));
  const [skills, setSkills] = useState(saved);
  const [removed, setRemoved] = useState<CvSkill[]>([]);
  const [showAllStrong, setShowAllStrong] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  const years = parseYears(yearsText, savedYears != null);
  // So theo giá trị, không theo chữ: gõ "1.5" khi đã lưu 1,5 không tính là thay đổi.
  const profileDirty = !years.ok || years.value !== savedYears || cleanTitle(titleText) !== savedTitle;
  const dirty = hasChanges(saved, skills) || profileDirty;
  const aliasesById = useMemo(() => new Map(taxonomy.map((t) => [t.id, t.aliases])), [taxonomy]);

  // Rời trang (đóng tab, tải lại) khi chưa lưu: trình duyệt hỏi lại.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function remove(skill: CvSkill) {
    setSkills((list) => list.filter((s) => s.skillId !== skill.skillId));
    // Kỹ năng tự thêm bỏ đi là mất luôn; kỹ năng đọc từ CV thì cho khôi phục.
    if (skill.level !== "user_added") setRemoved((list) => [...list, skill]);
    setSavedOk(false);
  }

  function restore(skill: CvSkill) {
    setRemoved((list) => list.filter((s) => s.skillId !== skill.skillId));
    setSkills((list) => sortSkills([...list, skill]));
    setSavedOk(false);
  }

  function add(skill: TaxonomySkill) {
    const back = removed.find((s) => s.skillId === skill.id);
    if (back) return restore(back); // chọn lại kỹ năng vừa xóa: giữ mức bằng chứng cũ
    setSkills((list) => addUserSkill(list, skill));
    setSavedOk(false);
  }

  async function save() {
    if (!years.ok) return;
    const title = cleanTitle(titleText);
    setSaving(true);
    setError(null);
    setSavedOk(false);
    const { error: rpcError } = await createClient()
      .schema("api")
      .rpc("confirm_cv_profile", {
        p_cv_id: cvId,
        p_years_exp: years.value, // null = giữ nguyên (chỉ khi CV chưa có số năm)
        p_target_title: title, // chuỗi rỗng = xóa chức danh
        p_skills: confirmPayload(skills),
      });
    if (rpcError) {
      setError(confirmErrorMessage(rpcError));
      setSaving(false);
      return;
    }
    const confirmed = skills.map((s) => ({ ...s, confirmed: true }));
    setSaved(confirmed);
    setSkills(confirmed);
    setRemoved([]);
    const newYears = years.value ?? savedYears;
    setSavedYears(newYears);
    setYearsText(formatYears(newYears));
    setSavedTitle(title);
    setTitleText(title);
    setLastSaved("vừa xong");
    setSaving(false);
    setSavedOk(true);
    router.refresh();
  }

  const byLevel = (level: EvidenceLevel) => skills.filter((s) => s.level === level);
  const strong = byLevel("strong");
  const listed = byLevel("listed");
  const userAdded = byLevel("user_added");
  const strongShown = showAllStrong ? strong : strong.slice(0, STRONG_PREVIEW);
  const strongHidden = strong.slice(STRONG_PREVIEW);
  const confirmed = lastSaved != null;
  const savedSummary = [
    savedTitle || null,
    savedYears != null ? `${formatYears(savedYears)} năm kinh nghiệm` : null,
    `${skills.length} kỹ năng`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="grid gap-4">
      <section aria-label="Thông tin chung" className="grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
        <div className="grid content-start gap-1.5">
          <label htmlFor={`${fieldId}-title`} className="text-sm font-medium">
            Chức danh mong muốn
          </label>
          <Input
            id={`${fieldId}-title`}
            value={titleText}
            maxLength={MAX_TITLE}
            placeholder="Ví dụ: Backend Developer"
            onChange={(e) => {
              setTitleText(e.target.value);
              setSavedOk(false);
            }}
            aria-describedby={`${fieldId}-title-hint`}
          />
          <p id={`${fieldId}-title-hint`} className="text-xs text-muted-foreground">
            {initialTitle
              ? "Gợi ý từ vị trí gần nhất trong CV, sửa được."
              : "CV chưa ghi rõ vị trí, hãy nhập vị trí bạn muốn ứng tuyển."}
          </p>
        </div>
        <div className="grid content-start gap-1.5">
          <label htmlFor={`${fieldId}-years`} className="text-sm font-medium">
            Tổng số năm kinh nghiệm
          </label>
          <div className="flex items-center gap-2">
            <Input
              id={`${fieldId}-years`}
              inputMode="decimal"
              value={yearsText}
              placeholder="Ví dụ: 1,5"
              className="w-24"
              onChange={(e) => {
                setYearsText(e.target.value);
                setSavedOk(false);
              }}
              aria-invalid={!years.ok || undefined}
              aria-describedby={`${fieldId}-years-hint`}
            />
            <span className="text-sm">năm</span>
          </div>
          <p
            id={`${fieldId}-years-hint`}
            className={cn("text-xs", years.ok ? "text-muted-foreground" : "text-destructive")}
          >
            {years.ok ? "Tính từ các mốc thời gian trong CV. Nhập 0 nếu chưa đi làm." : years.error}
          </p>
        </div>
      </section>

      {skills.length === 0 && removed.length === 0 && (
        <Alert>
          <AlertTitle>Chưa thấy kỹ năng nào trong CV</AlertTitle>
          <AlertDescription>Bạn vẫn có thể tự thêm kỹ năng từ từ điển ở bên dưới.</AlertDescription>
        </Alert>
      )}

      <LevelSection level="strong" count={strong.length}>
        {strong.length === 0 ? (
          <Empty>Không có kỹ năng nào được dùng trong Kinh nghiệm / Dự án.</Empty>
        ) : (
          <ul className="grid gap-2">
            {strongShown.map((s) => (
              <li key={s.skillId} className="flex items-start gap-3 rounded-lg border p-3">
                <div className="grid min-w-0 flex-1 gap-1">
                  <span className="font-medium">
                    {s.name}
                    {s.years != null && s.years > 0 && (
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        ≈ {s.years.toLocaleString("vi-VN")} năm
                      </span>
                    )}
                  </span>
                  {s.evidence && (
                    <Evidence text={s.evidence} terms={[s.name, ...(aliasesById.get(s.skillId) ?? [])]} />
                  )}
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => remove(s)} aria-label={`Xóa kỹ năng ${s.name}`}>
                  Xóa
                </Button>
              </li>
            ))}
          </ul>
        )}
        {strongHidden.length > 0 && (
          <button
            type="button"
            className="justify-self-start text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
            onClick={() => setShowAllStrong((v) => !v)}
            aria-expanded={showAllStrong}
          >
            {showAllStrong
              ? "Thu gọn"
              : `+ ${strongHidden.length} kỹ năng khác (${strongHidden.map((s) => s.name).join(", ")}) · Xem tất cả`}
          </button>
        )}
      </LevelSection>

      <LevelSection level="listed" count={listed.length}>
        {listed.length === 0 ? (
          <Empty>Không có kỹ năng nào chỉ được liệt kê.</Empty>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {listed.map((s) => (
              <Chip key={s.skillId} skill={s} title={s.evidence ?? undefined} onRemove={() => remove(s)} />
            ))}
          </ul>
        )}
      </LevelSection>

      <LevelSection level="user_added" count={userAdded.length}>
        {userAdded.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {userAdded.map((s) => (
              <Chip key={s.skillId} skill={s} onRemove={() => remove(s)} />
            ))}
          </ul>
        )}
        <SkillPicker taxonomy={taxonomy} excludeIds={new Set(skills.map((s) => s.skillId))} onPick={add} />
      </LevelSection>

      {removed.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>Đã bỏ:</span>
          {removed.map((s) => (
            <Button key={s.skillId} type="button" variant="outline" size="xs" onClick={() => restore(s)}>
              <Undo2 aria-hidden /> {s.name}
              <span className="sr-only">(khôi phục)</span>
            </Button>
          ))}
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <XCircle aria-hidden />
          <AlertTitle>Chưa lưu được hồ sơ</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {savedOk && (
        <Alert>
          <CheckCircle2 aria-hidden />
          <AlertTitle>Đã lưu hồ sơ</AlertTitle>
          <AlertDescription>{savedSummary}. Tải lại trang vẫn thấy dữ liệu đã lưu.</AlertDescription>
        </Alert>
      )}

      <div className="sticky bottom-0 flex flex-wrap items-center gap-3 border-t bg-background py-3">
        <Link
          href="/ho-so"
          className={buttonVariants({ variant: "ghost" })}
          onClick={(e) => {
            if (dirty && !window.confirm(LEAVE_PROMPT)) e.preventDefault();
          }}
        >
          ← Hồ sơ của tôi
        </Link>
        <span className="ml-auto text-xs text-muted-foreground" aria-live="polite">
          {dirty ? "Chưa lưu thay đổi" : confirmed ? `Đã lưu ${lastSaved === "vừa xong" ? "vừa xong" : `lúc ${lastSaved}`}` : ""}
        </span>
        <Button type="button" onClick={() => void save()} disabled={saving || !years.ok || (!dirty && confirmed)}>
          {saving && <LoaderCircle className="animate-spin" aria-hidden />}
          Lưu hồ sơ
        </Button>
      </div>

      <details className="rounded-lg border p-3 text-sm text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">Mức bằng chứng nghĩa là gì?</summary>
        <ul className="mt-2 grid gap-1">
          <li>
            <b className="text-foreground">Có bằng chứng</b>: dùng trong kinh nghiệm/dự án, kèm câu trích.
          </li>
          <li>
            <b className="text-foreground">Chỉ liệt kê</b>: chỉ ghi tên trong mục Kỹ năng.
          </li>
          <li>
            <b className="text-foreground">Tự thêm</b>: bạn bổ sung, không có trong CV.
          </li>
          <li>Khi chấm việc phù hợp, &quot;Có bằng chứng&quot; được tính nặng hơn &quot;Chỉ liệt kê&quot;.</li>
          <li>Họ tên, email, số điện thoại, địa chỉ trong câu trích đã được che thành [ĐÃ CHE].</li>
        </ul>
      </details>
    </div>
  );
}

function LevelSection({ level, count, children }: { level: EvidenceLevel; count: number; children: React.ReactNode }) {
  const info = LEVEL_INFO[level];
  const headingId = `level-${level}`;
  return (
    <section aria-labelledby={headingId} className="grid gap-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h2 id={headingId} className="font-semibold">
          {info.title}
        </h2>
        <span className="rounded-full bg-muted px-2 text-xs font-medium">{count}</span>
        <span className="text-sm text-muted-foreground">{info.hint}</span>
      </div>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

/** Câu trích đã che PII, in đậm tên kỹ năng. */
function Evidence({ text, terms }: { text: string; terms: string[] }) {
  const parts = splitEvidence(text, terms);
  return (
    <q className="text-sm text-muted-foreground">
      {parts ? (
        <>
          {parts[0]}
          <mark className="rounded-sm bg-primary/15 px-0.5 font-semibold text-foreground">{parts[1]}</mark>
          {parts[2]}
        </>
      ) : (
        text
      )}
    </q>
  );
}

function Chip({ skill, title, onRemove }: { skill: CvSkill; title?: string; onRemove: () => void }) {
  const userAdded = skill.level === "user_added";
  return (
    <li
      title={title}
      className={cn(
        "flex items-center gap-1 rounded-full border py-0.5 pr-1 pl-2.5 text-sm",
        userAdded && "border-dashed border-primary",
      )}
    >
      {skill.name}
      {userAdded && <span className="text-xs text-muted-foreground">· Tự thêm</span>}
      <button
        type="button"
        onClick={onRemove}
        className="grid size-5 place-items-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label={`Xóa kỹ năng ${skill.name}`}
      >
        <X className="size-3.5" aria-hidden />
      </button>
    </li>
  );
}

/** Ô thêm kỹ năng có gợi ý (combobox): chỉ nhận kỹ năng có trong từ điển. */
function SkillPicker({
  taxonomy,
  excludeIds,
  onPick,
}: {
  taxonomy: TaxonomySkill[];
  excludeIds: ReadonlySet<number>;
  onPick: (skill: TaxonomySkill) => void;
}) {
  const id = useId();
  const listId = `${id}-list`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const options = searchSkills(taxonomy, query, excludeIds);
  const showList = open && query.trim() !== "";

  function pick(skill: TaxonomySkill | undefined) {
    if (!skill) return;
    onPick(skill);
    setQuery("");
    setActive(0);
    setOpen(false);
    inputRef.current?.focus();
  }

  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        Thêm kỹ năng
      </label>
      <div className="relative flex gap-2">
        <Input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && options[active] ? `${listId}-${options[active].id}` : undefined}
          autoComplete="off"
          placeholder="Gõ tên kỹ năng, ví dụ: kafka"
          className="max-w-xs"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((i) => Math.min(i + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              pick(options[active]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        />
        <Button type="button" variant="outline" onClick={() => pick(options[active])} disabled={options.length === 0}>
          <Plus aria-hidden /> Thêm
        </Button>
        {showList && (
          <ul
            id={listId}
            role="listbox"
            aria-label="Gợi ý kỹ năng"
            className="absolute top-full left-0 z-10 mt-1 grid max-h-64 w-full max-w-xs overflow-auto rounded-lg border bg-popover p-1 text-sm shadow-md"
          >
            {options.length === 0 ? (
              <li className="px-2 py-1.5 text-muted-foreground">Không có trong từ điển kỹ năng</li>
            ) : (
              options.map((o, i) => (
                <li
                  key={o.id}
                  id={`${listId}-${o.id}`}
                  role="option"
                  aria-selected={i === active}
                  className={cn("cursor-pointer rounded-md px-2 py-1.5", i === active && "bg-muted")}
                  onMouseEnter={() => setActive(i)}
                  // mousedown chạy trước blur của ô nhập, nên chọn được trước khi danh sách đóng.
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(o);
                  }}
                >
                  {o.name}
                </li>
              ))
            )}
          </ul>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Gợi ý lấy từ từ điển kỹ năng của hệ thống (gõ không dấu được). Không nhận kỹ năng ngoài từ điển.
      </p>
    </div>
  );
}
