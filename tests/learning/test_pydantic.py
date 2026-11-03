"""Spike TASK-D001: Pydantic v2 + PyYAML trên model Skill (chỉ để học, chưa phải taxonomy.py)."""

from typing import Self

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

# 1 = nhóm lớn, 2 = kỹ năng cụ thể, 3 = framework/công cụ con
ALLOWED_LEVELS = {1, 2, 3}


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


def load_skill(text: str) -> Skill:
    return Skill.model_validate(yaml.safe_load(text))


def test_level_out_of_domain():
    with pytest.raises(ValidationError, match=r"level phải thuộc \[1, 2, 3\], nhận 7"):
        load_skill("id: python\nlevel: 7\nparent: programming\n")


def test_ambiguous_without_context():
    with pytest.raises(ValidationError, match="go: ambiguous=True thì context không được rỗng"):
        load_skill("id: go\nlevel: 2\nparent: programming\nambiguous: true\n")


def test_empty_id():
    with pytest.raises(ValidationError, match="id không được rỗng"):
        load_skill("id: '   '\nlevel: 1\n")
