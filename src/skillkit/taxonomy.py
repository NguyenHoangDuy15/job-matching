"""Nạp skills.yaml thành Taxonomy và bắt lỗi dữ liệu ngay lúc nạp."""

import unicodedata
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

# 1 = nhóm lớn, 2 = kỹ năng cụ thể, 3 = framework/công cụ con
ALLOWED_LEVELS = {1, 2, 3}


class TaxonomyError(ValueError):
    """Dữ liệu skills.yaml sai; thông điệp nêu rõ id/alias lỗi."""


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    id: str
    aliases: list[str] = []
    parent: str | None = None
    level: int
    ambiguous: bool = False
    context: list[str] = []

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
        return self


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
    return unicodedata.normalize("NFC", text).lower()


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
        for term in [s.id, *s.aliases]:
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
