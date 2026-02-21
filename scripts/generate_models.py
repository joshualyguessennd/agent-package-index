"""Parse SQL migrations and generate SQLAlchemy models in app/models.py."""

import re
import sys
from pathlib import Path

from app.schemas.model_gen import ColumnDef, EnumDef, RelationshipDef, TableDef

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "app" / "models.py"

# SQL type -> (SQLAlchemy type, needs import)
TYPE_MAP: dict[str, tuple[str, str]] = {
    "SERIAL": ("Integer", "Integer"),
    "BIGSERIAL": ("BigInteger", "BigInteger"),
    "INTEGER": ("Integer", "Integer"),
    "BIGINT": ("BigInteger", "BigInteger"),
    "SMALLINT": ("SmallInteger", "SmallInteger"),
    "TEXT": ("Text", "Text"),
    "BOOLEAN": ("Boolean", "Boolean"),
    "DATE": ("Date", "Date"),
    "TIMESTAMP": ("DateTime", "DateTime"),
    "TIMESTAMPTZ": ("DateTime(timezone=True)", "DateTime"),
    "FLOAT": ("Float", "Float"),
    "DOUBLE PRECISION": ("Float", "Float"),
    "JSONB": ("JSON", "JSON"),
    "JSON": ("JSON", "JSON"),
    "UUID": ("Uuid", "Uuid"),
    "TSVECTOR": ("Text", "Text"),
}

# Pluralization for relationship attribute names
_IRREGULAR_PLURALS: dict[str, str] = {
    "vulnerability": "vulnerabilities",
    "crawl_state": "crawl_states",
}


def _pluralize(name: str) -> str:
    """Simple pluralization for relationship back-references."""
    if name in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[name]
    if name.endswith("s"):
        return name + "es"
    if name.endswith("y"):
        return name[:-1] + "ies"
    return name + "s"


def parse_enums(sql: str) -> list[EnumDef]:
    """Extract CREATE TYPE ... AS ENUM definitions from SQL."""
    enums: list[EnumDef] = []
    pattern = re.compile(
        r"CREATE\s+TYPE\s+(\w+)\s+AS\s+ENUM\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        type_name = match.group(1).lower()
        values_str = match.group(2)
        values = [v.strip().strip("'\"") for v in values_str.split(",")]
        enums.append(EnumDef(name=type_name, values=values))
    return enums


def _enum_names(enums: list[EnumDef]) -> set[str]:
    return {e.name for e in enums}


def sql_type_to_sa(sql_type: str, enums: list[EnumDef]) -> tuple[str, set[str]]:
    """Convert a SQL type string to a SQLAlchemy Column type expression and required imports."""
    imports: set[str] = set()
    upper = sql_type.upper().strip()
    raw = sql_type.strip()
    enum_names = _enum_names(enums)

    array_match = re.match(r"(\w+)\[\]", upper)
    if array_match:
        base_type = array_match.group(1)
        inner_expr, inner_imports = sql_type_to_sa(base_type, enums)
        imports.update(inner_imports)
        imports.add("ARRAY")
        return f"ARRAY({inner_expr})", imports

    lower = raw.lower()
    if lower in enum_names:
        imports.add("Enum")
        enum_class = table_to_class_name(lower)
        return f"Enum({enum_class}, name='{lower}')", imports

    paren_match = re.match(r"(\w+)\((.+)\)", upper)
    if paren_match:
        base, args = paren_match.group(1), paren_match.group(2)
        if base in ("VARCHAR", "CHAR", "CHARACTER VARYING"):
            imports.add("String")
            return f"String({args})", imports
        if base in ("NUMERIC", "DECIMAL"):
            imports.add("Numeric")
            return f"Numeric({args})", imports

    if upper in TYPE_MAP:
        expr, imp = TYPE_MAP[upper]
        imports.add(imp)
        return expr, imports

    imports.add("String")
    return "String", imports


def parse_column(line: str, enums: list[EnumDef]) -> ColumnDef | None:
    """Parse a single column definition line from a CREATE TABLE body."""
    line = line.strip().rstrip(",")
    skip_prefixes = (
        "CONSTRAINT", "PRIMARY KEY", "UNIQUE(", "UNIQUE (", "CHECK", "FOREIGN KEY",
    )
    if not line or line.upper().startswith(skip_prefixes):
        return None

    m = re.match(r"(\w+)\s+(.+)", line)
    if not m:
        return None

    col_name: str = m.group(1)
    rest: str = m.group(2)

    fk_ref: str | None = None
    fk_table: str | None = None
    fk_match = re.search(
        r"REFERENCES\s+(\w+)\((\w+)\)(?:\s+ON\s+DELETE\s+(\w+))?",
        rest,
        re.IGNORECASE,
    )
    if fk_match:
        fk_table = fk_match.group(1)
        fk_col = fk_match.group(2)
        fk_ref = f"{fk_table}.{fk_col}"
        rest = rest[: fk_match.start()] + rest[fk_match.end() :]

    enum_names = _enum_names(enums)

    array_type_match = re.match(r"(\w+)\[\]\s*(.*)", rest, re.IGNORECASE)
    if array_type_match:
        sql_type = array_type_match.group(1) + "[]"
        constraint_str = array_type_match.group(2).strip()
    else:
        type_match = re.match(
            r"(\w+(?:\s+\w+)?(?:\([^)]*\))?)\s*(.*)",
            rest,
            re.IGNORECASE,
        )
        if not type_match:
            return None

        sql_type_raw: str = type_match.group(1).strip()
        constraint_str: str = type_match.group(2).strip()

        parts = sql_type_raw.split()
        known_multiword = {"DOUBLE PRECISION", "CHARACTER VARYING"}
        if len(parts) == 2 and " ".join(parts).upper() not in known_multiword:
            if parts[1].lower() in enum_names:
                sql_type = parts[1]
                constraint_str = ""
            else:
                sql_type = parts[0]
                constraint_str = parts[1] + " " + constraint_str
        else:
            sql_type = sql_type_raw

    upper_constraints: str = constraint_str.upper()
    primary_key: bool = "PRIMARY KEY" in upper_constraints
    not_null: bool = "NOT NULL" in upper_constraints
    unique: bool = "UNIQUE" in upper_constraints

    default: str | None = None
    default_pat = (
        r"DEFAULT\s+(.+?)"
        r"(?:\s+NOT\s+NULL|\s+UNIQUE|\s+PRIMARY\s+KEY|\s+REFERENCES|,|$)"
    )
    default_match = re.search(default_pat, constraint_str, re.IGNORECASE)
    if default_match:
        default = default_match.group(1).strip()

    sa_type, imports = sql_type_to_sa(sql_type, enums)
    is_serial: bool = sql_type.upper() in ("SERIAL", "BIGSERIAL")

    return ColumnDef(
        name=col_name,
        sa_type=sa_type,
        imports=imports,
        primary_key=primary_key or is_serial,
        nullable=not (not_null or primary_key or is_serial),
        unique=unique,
        default=default,
        autoincrement=is_serial,
        fk_ref=fk_ref,
        fk_table=fk_table,
    )


def parse_create_tables(sql: str, enums: list[EnumDef]) -> list[TableDef]:
    """Extract all CREATE TABLE statements from SQL text."""
    tables: list[TableDef] = []
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(sql):
        table_name: str = match.group(1)
        body: str = match.group(2)
        columns: list[ColumnDef] = []
        for line in body.split("\n"):
            col = parse_column(line, enums)
            if col:
                columns.append(col)
        tables.append(TableDef(name=table_name, columns=columns))
    return tables


def build_relationships(tables: list[TableDef]) -> None:
    """Populate relationship definitions on tables based on FK columns."""
    table_map: dict[str, TableDef] = {t.name: t for t in tables}

    for child_table in tables:
        for col in child_table.columns:
            if col.fk_table and col.fk_table in table_map:
                parent_table = table_map[col.fk_table]
                parent_class: str = table_to_class_name(parent_table.name)
                child_class: str = table_to_class_name(child_table.name)

                # Attribute name on the child (singular parent name)
                child_attr: str = parent_table.name
                # Attribute name on the parent (plural child name)
                parent_attr: str = _pluralize(child_table.name)

                child_table.relationships.append(
                    RelationshipDef(
                        attr_name=child_attr,
                        target_class=parent_class,
                        back_populates=parent_attr,
                    )
                )
                parent_table.relationships.append(
                    RelationshipDef(
                        attr_name=parent_attr,
                        target_class=child_class,
                        back_populates=child_attr,
                    )
                )


def table_to_class_name(table_name: str) -> str:
    """Convert snake_case table name to PascalCase class name."""
    return "".join(word.capitalize() for word in table_name.split("_"))


def generate_column_line(col: ColumnDef) -> str:
    """Generate a single SQLAlchemy Column(...) line."""
    args: list[str] = [col.sa_type]
    if col.fk_ref:
        args.append(f"ForeignKey('{col.fk_ref}')")
        col.imports.add("ForeignKey")
    if col.primary_key:
        args.append("primary_key=True")
    if col.autoincrement:
        args.append("autoincrement=True")
    if not col.nullable and not col.primary_key:
        args.append("nullable=False")
    if col.unique:
        args.append("unique=True")
    if col.default is not None:
        default_val: str = col.default.strip("'\"")
        upper_default: str = default_val.upper()
        if upper_default in ("TRUE", "FALSE"):
            args.append(f"server_default=text('{default_val}')")
            col.imports.add("text")
        elif upper_default.startswith("NOW(") or upper_default.startswith("CURRENT_TIMESTAMP"):
            args.append("server_default=func.now()")
            col.imports.add("func")
        else:
            args.append(f"server_default=text('{default_val}')")
            col.imports.add("text")
    return f"    {col.name} = Column({', '.join(args)})"


def generate_relationship_line(rel: RelationshipDef) -> str:
    """Generate a single relationship(...) line."""
    return (
        f"    {rel.attr_name} = relationship("
        f'"{rel.target_class}", back_populates="{rel.back_populates}")'
    )


def generate_enum_class(enum_def: EnumDef) -> str:
    """Generate a Python enum class from a SQL ENUM type."""
    class_name: str = table_to_class_name(enum_def.name)
    lines: list[str] = [f"class {class_name}(enum.Enum):"]
    for val in enum_def.values:
        lines.append(f"    {val} = '{val}'")
    return "\n".join(lines)


def generate_models_source(tables: list[TableDef], enums: list[EnumDef]) -> str:
    """Generate the full models.py source code."""
    all_imports: set[str] = {"Column"}
    orm_imports: set[str] = {"DeclarativeBase"}
    all_lines: list[str] = []
    has_enums: bool = bool(enums)
    has_array: bool = False
    has_relationships: bool = False

    for table in tables:
        class_name: str = table_to_class_name(table.name)
        col_lines: list[str] = []
        for col in table.columns:
            col_lines.append(generate_column_line(col))
            all_imports.update(col.imports)
            if "ARRAY" in col.sa_type:
                has_array = True

        rel_lines: list[str] = []
        seen_attrs: set[str] = set()
        for rel in table.relationships:
            if rel.attr_name not in seen_attrs:
                rel_lines.append(generate_relationship_line(rel))
                seen_attrs.add(rel.attr_name)
                has_relationships = True

        body: str = "\n".join(col_lines)
        if rel_lines:
            body += "\n\n" + "\n".join(rel_lines)

        block = (
            f"\n\nclass {class_name}(Base):\n"
            f"    __tablename__ = \"{table.name}\"\n\n"
            + body
        )
        all_lines.append(block)

    if has_array:
        all_imports.add("ARRAY")
    if has_enums:
        all_imports.add("Enum")
    if has_relationships:
        orm_imports.add("relationship")

    sorted_imports: list[str] = sorted(all_imports)
    sorted_orm: list[str] = sorted(orm_imports)
    import_lines: list[str] = [
        "# Auto-generated by scripts/generate_models.py — do not edit manually.",
        "# Run `make generate-models` to regenerate from SQL migrations.",
        "",
    ]
    if has_enums:
        import_lines.append("import enum")
        import_lines.append("")
    import_lines.append(f"from sqlalchemy import {', '.join(sorted_imports)}")
    import_lines.append(f"from sqlalchemy.orm import {', '.join(sorted_orm)}")

    enum_blocks: list[str] = []
    if has_enums:
        for enum_def in enums:
            enum_blocks.append("\n\n" + generate_enum_class(enum_def))

    header: str = "\n".join(import_lines)
    header += "\n\n\nclass Base(DeclarativeBase):\n    pass"

    return header + "".join(enum_blocks) + "".join(all_lines) + "\n"


def main() -> None:
    sql_files: list[Path] = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print("No migration files found in", MIGRATIONS_DIR)
        sys.exit(1)

    combined_sql: str = ""
    for f in sql_files:
        combined_sql += f.read_text() + "\n"

    enums: list[EnumDef] = parse_enums(combined_sql)
    tables: list[TableDef] = parse_create_tables(combined_sql, enums)
    if not tables:
        print("No CREATE TABLE statements found.")
        sys.exit(1)

    build_relationships(tables)

    source: str = generate_models_source(tables, enums)
    OUTPUT_FILE.write_text(source)
    print(f"Generated {len(tables)} model(s) with {len(enums)} enum(s) -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
