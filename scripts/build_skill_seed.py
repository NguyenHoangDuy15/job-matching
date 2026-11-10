"""Sinh db/seed/seed_skills.sql từ config/skills.yaml (S2-D03). Không sửa tay file SQL.

Chạy: PYTHONPATH=src uv run python scripts/build_skill_seed.py
CI (tests/unit/test_skill_seed.py) báo đỏ nếu file SQL lệch với YAML.

- ref.skills: mọi mục level 2–3 (level 1 là nhóm, ứng với ref.skill_categories).
- ref.skill_aliases: tên chuẩn + alias, chuẩn hóa NFC + chữ thường, GIỮ DẤU (khớp
  skillkit.matcher). Cách viết nhập nhằng có needs_context = true và context_rule (jsonb).
- Kỹ năng/alias bị xóa khỏi YAML: skill chuyển is_active = false, alias bị xóa.
- Cây cha–con: ref.skills.parent_id (migration 0003). Kỹ năng level 3 trỏ về kỹ năng
  level 2; level 2 có parent_id = NULL (nhóm level 1 nằm ở ref.skill_categories).
  DB chưa chạy 0003 thì bước này tự bỏ qua.
"""

import json
import sys
from pathlib import Path

from skillkit import load_taxonomy
from skillkit.matcher import prepare
from skillkit.taxonomy import Skill, Taxonomy

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "config" / "skills.yaml"
SQL_PATH = ROOT / "db" / "seed" / "seed_skills.sql"
CATEGORIES = range(1, 8)  # ref.skill_categories trong seed_reference_data.sql


class SeedError(ValueError):
    pass


def _q(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return "'" + str(value).replace("'", "''") + "'"


def alias_norm(term: str) -> str:
    return prepare(term)[1]


def context_rule(skill: Skill) -> dict:
    rule = skill.rule
    return {
        "context": list(skill.context),
        "forms": list(rule.forms) if rule else [],
        "reject": list(rule.reject) if rule else [],
        "veto": list(rule.veto) if rule else [],
        "window": rule.window if rule else 6,
    }


def rows(taxonomy: Taxonomy) -> tuple[list[tuple], list[tuple]]:
    skills, aliases = [], []
    for skill in sorted((s for s in taxonomy if s.level > 1), key=lambda s: s.id):
        category = taxonomy.category_of(skill.id)
        if not skill.name:
            raise SeedError(f"{skill.id}: thiếu name")
        if category not in CATEGORIES:
            raise SeedError(f"{skill.id}: category {category} không có trong ref.skill_categories")
        skills.append((skill.id, skill.name, category, skill.kind))
        ambiguous = skill.ambiguous_terms()
        rule = json.dumps(context_rule(skill), ensure_ascii=False)
        for term in dict.fromkeys(alias_norm(t) for t in skill.terms()):
            needs = term in ambiguous
            aliases.append((term, skill.id, needs, rule if needs else None))
    return skills, aliases


def parent_pairs(taxonomy: Taxonomy) -> list[tuple[str, str | None]]:
    """(slug, slug cha) cho mọi kỹ năng; cha là None với kỹ năng level 2."""
    return [
        (s.id, s.parent if s.level == 3 else None)
        for s in sorted((s for s in taxonomy if s.level > 1), key=lambda s: s.id)
    ]


def render(taxonomy: Taxonomy) -> str:
    skills, aliases = rows(taxonomy)
    tree_values = ",\n".join(
        f"      ({_q(slug)}, {_q(parent)})" for slug, parent in parent_pairs(taxonomy)
    )
    skill_values = ",\n".join(
        f"  ({_q(slug)}, {_q(name)}, {cat}, {_q(kind)}, 'manual')"
        for slug, name, cat, kind in skills
    )
    alias_list = ",\n".join("  " + _q(a[0]) for a in aliases)
    slug_list = ", ".join(_q(s[0]) for s in skills)
    alias_values = ",\n".join(
        f"  ({_q(a)}, {_q(slug)}, {_q(needs)}, {_q(rule)})" for a, slug, needs, rule in aliases
    )
    return f"""-- =====================================================================
--  Từ điển kỹ năng (S2-D03, US-10/AC2) — SINH TỰ ĐỘNG từ config/skills.yaml.
--  Không sửa tay: chạy `PYTHONPATH=src uv run python scripts/build_skill_seed.py`.
--  Cần chạy sau migration 0001 và seed_reference_data.sql (ref.skill_categories).
--  {len(skills)} kỹ năng, {len(aliases)} cách viết.
-- =====================================================================

insert into ref.skills (slug, name, category_id, kind, source) values
{skill_values}
on conflict (slug) do update
  set name = excluded.name, category_id = excluded.category_id, kind = excluded.kind,
      source = excluded.source, is_active = true;

update ref.skills set is_active = false
where slug not in ({slug_list});

delete from ref.skill_aliases
where alias_norm not in (
{alias_list}
);

insert into ref.skill_aliases (alias_norm, skill_id, needs_context, context_rule)
select v.alias_norm, s.id, v.needs_context, v.context_rule::jsonb
from (values
{alias_values}
) as v (alias_norm, slug, needs_context, context_rule)
join ref.skills s on s.slug = v.slug
on conflict (alias_norm) do update
  set skill_id = excluded.skill_id, needs_context = excluded.needs_context,
      context_rule = excluded.context_rule;

-- Cây kỹ năng (cần migration 0003). Hai bước để không vướng trigger ref.check_skill_parent
-- (cây 2 tầng): (a) bỏ cha của mọi kỹ năng có cha sai, (b) gán cha cho kỹ năng còn thiếu.
do $$
begin
  if not exists (select 1 from information_schema.columns
                  where table_schema = 'ref' and table_name = 'skills'
                    and column_name = 'parent_id') then
    raise notice 'ref.skills chưa có parent_id (migration 0003): bỏ qua cây kỹ năng';
    return;
  end if;

  drop table if exists pg_temp.skill_tree;
  create temp table skill_tree (slug text primary key, parent_slug text) on commit drop;
  insert into skill_tree values
{tree_values};

  update ref.skills s set parent_id = null
    from skill_tree t
    left join ref.skills p on p.slug = t.parent_slug
   where s.slug = t.slug and s.parent_id is distinct from p.id and s.parent_id is not null;

  update ref.skills s set parent_id = p.id
    from skill_tree t
    join ref.skills p on p.slug = t.parent_slug
   where s.slug = t.slug and s.parent_id is null;
end $$;
"""


def main() -> int:
    sql = render(load_taxonomy(YAML_PATH))
    SQL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQL_PATH.write_text(sql, encoding="utf-8")
    print(f"{SQL_PATH.relative_to(ROOT)}: {sql.splitlines()[4].strip('- ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
