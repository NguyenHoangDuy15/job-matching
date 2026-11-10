"""Nạp skills.yaml thành Taxonomy và bắt lỗi dữ liệu ngay lúc nạp."""

import unicodedata
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

# 1 = nhóm lớn, 2 = kỹ năng cụ thể, 3 = framework/công cụ con
ALLOWED_LEVELS = {1, 2, 3}

# Khớp CHECK của ref.skills.kind (migration 0001).
Kind = Literal["hard", "tool", "language", "framework", "cloud", "soft", "domain"]


class TaxonomyError(ValueError):
    """Dữ liệu skills.yaml sai; thông điệp nêu rõ id/alias lỗi."""


class ContextRule(BaseModel):
    """Quy tắc cho từ nhập nhằng ("Go", "R", "C"...). Lưu vào ref.skill_aliases.context_rule.

    Một lần khớp `terms` chỉ được nhận khi: đúng dạng chữ trong `forms` (nếu có), không nằm
    trong cụm `reject`, không có từ `veto` trong cửa sổ, và (đứng trong danh sách kỹ năng
    hoặc có từ ngữ cảnh của skill trong cửa sổ `window` token).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    terms: list[str]
    forms: list[str] = []
    reject: list[str] = []
    veto: list[str] = []
    window: int = 6


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    id: str
    name: str | None = None  # tên chuẩn hiển thị (US-10/AC2); bắt buộc khi sinh seed DB
    aliases: list[str] = []
    parent: str | None = None
    level: int
    kind: Kind = "hard"
    category: int | None = None  # id ref.skill_categories; level 1 bắt buộc, level 2–3 ghi đè
    ambiguous: bool = False
    context: list[str] = []
    rule: ContextRule | None = None

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("id không được rỗng")
        return v

    @field_validator("level")
    @classmethod
    def level_in_domain(cls, v: int) -> int:
        if v not in ALLOWED_LEVELS:
            raise ValueError(f"level phải thuộc {sorted(ALLOWED_LEVELS)}, nhận {v}")
        return v

    # Không dùng field_validator("context"): nó không chạy khi context lấy giá trị mặc định.
    @model_validator(mode="after")
    def ambiguous_needs_context(self) -> Self:
        if self.ambiguous and not self.context:
            raise ValueError(f"{self.id}: ambiguous=True thì context không được rỗng")
        if self.rule is not None and not self.ambiguous:
            raise ValueError(f"{self.id}: có rule thì phải ambiguous=True")
        if self.rule is not None:
            known = {_norm(t) for t in self.terms()}
            unknown = [t for t in self.rule.terms if _norm(t) not in known]
            if unknown:
                raise ValueError(f"{self.id}: rule.terms {unknown} không có trong name/aliases")
        return self

    def terms(self) -> list[str]:
        """Các cách viết dùng để khớp trong JD: tên chuẩn + alias (không gồm id)."""
        return [t for t in [self.name, *self.aliases] if t]

    def ambiguous_terms(self) -> set[str]:
        """Cách viết cần kiểm tra ngữ cảnh; ambiguous mà không có rule thì mọi cách viết."""
        if not self.ambiguous:
            return set()
        source = self.rule.terms if self.rule else self.terms()
        return {_norm(t) for t in source}


class Taxonomy:
    def __init__(self, skills: list[Skill]) -> None:
        self._by_id = {s.id: s for s in skills}
        self._children: dict[str, list[str]] = {s.id: [] for s in skills}
        for s in sorted(skills, key=lambda s: s.id):
            if s.parent is not None:
                self._children[s.parent].append(s.id)

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, skill_id: str) -> Skill:
        return self._by_id[skill_id]

    def ancestors(self, skill_id: str) -> list[str]:
        """Các mục tổ tiên, từ cha đi lên gốc."""
        result: list[str] = []
        current = self._by_id[skill_id].parent
        while current is not None:
            result.append(current)
            current = self._by_id[current].parent
        return result

    def children(self, skill_id: str) -> list[str]:
        """Con trực tiếp, sắp theo id."""
        return list(self._children[skill_id])

    def __iter__(self):
        return iter(self._by_id.values())

    def root(self, skill_id: str) -> Skill:
        """Mục level 1 chứa skill này."""
        chain = [skill_id, *self.ancestors(skill_id)]
        return self._by_id[chain[-1]]

    def category_of(self, skill_id: str) -> int | None:
        """Nhóm của skill: tự ghi thì dùng, không thì lấy của tổ tiên gần nhất."""
        for sid in [skill_id, *self.ancestors(skill_id)]:
            if self._by_id[sid].category is not None:
                return self._by_id[sid].category
        return None

    def family_members(self, skill_id: str) -> list[str]:
        """Chính nó + tổ tiên + mọi hậu duệ, sắp theo id; không gồm anh em cùng cha."""
        members = {skill_id, *self.ancestors(skill_id)}
        stack = self.children(skill_id)
        while stack:
            current = stack.pop()
            members.add(current)
            stack.extend(self._children[current])
        return sorted(members)


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def _parse_skill(entry: Any, index: int) -> Skill:
    try:
        # strict: YAML ghi level: "2" hay level: yes phải bị báo, không âm thầm ép kiểu.
        return Skill.model_validate(entry, strict=True)
    except ValidationError as e:
        label = entry.get("id", "?") if isinstance(entry, dict) else "?"
        detail = "; ".join(" ".join([*map(str, err["loc"]), err["msg"]]) for err in e.errors())
        raise TaxonomyError(f"skills[{index}] (id={label}): {detail}") from e


def _check_unique_ids(skills: list[Skill]) -> None:
    seen: set[str] = set()
    for s in skills:
        if s.id in seen:
            raise TaxonomyError(f"trùng id '{s.id}'")
        seen.add(s.id)


def _check_unique_terms(skills: list[Skill]) -> None:
    # Gom cả id lẫn alias: khi trích kỹ năng, một từ khóa chỉ được trỏ tới một skill.
    owners: dict[str, str] = {}
    for s in skills:
        for term in dict.fromkeys(_norm(t) for t in [s.id, *s.terms()]):
            owner = owners.setdefault(_norm(term), s.id)
            if owner != s.id:
                raise TaxonomyError(f"alias '{term}' trùng giữa {owner} và {s.id}")


def _check_parents(skills: list[Skill]) -> None:
    by_id = {s.id: s for s in skills}
    for s in skills:
        if s.parent is not None and s.parent not in by_id:
            raise TaxonomyError(f"{s.id}: parent '{s.parent}' không tồn tại")

    # Kiểm vòng lặp trước luật level: mọi vòng lặp đều vi phạm luật level, nên làm ngược lại
    # thì thông điệp sẽ báo sai level thay vì nguyên nhân thật.
    for s in skills:
        seen = {s.id}
        current = s.parent
        while current is not None:
            if current in seen:
                raise TaxonomyError(f"{s.id}: vòng lặp parent qua '{current}'")
            seen.add(current)
            current = by_id[current].parent

    for s in skills:
        if s.level == 1 and s.parent is not None:
            raise TaxonomyError(f"{s.id}: level 1 không được có parent")
        if s.level > 1 and s.parent is None:
            raise TaxonomyError(f"{s.id}: level {s.level} bắt buộc có parent")
        if s.parent is not None and by_id[s.parent].level != s.level - 1:
            raise TaxonomyError(
                f"{s.id}: level {s.level} phải có parent level {s.level - 1}, "
                f"nhưng '{s.parent}' là level {by_id[s.parent].level}"
            )


def load_taxonomy(path: str | Path) -> Taxonomy:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise TaxonomyError(f"{path}: YAML sai cú pháp: {e}") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("skills"), list):
        raise TaxonomyError(f"{path}: phải có khóa gốc 'skills' chứa một danh sách")

    skills = [_parse_skill(entry, i) for i, entry in enumerate(raw["skills"])]
    _check_unique_ids(skills)
    _check_unique_terms(skills)
    _check_parents(skills)
    return Taxonomy(skills)
