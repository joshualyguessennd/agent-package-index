"""Schemas for the SQL-to-SQLAlchemy model generator."""

from dataclasses import dataclass, field


@dataclass
class ColumnDef:
    """Parsed column definition from a CREATE TABLE statement."""

    name: str
    sa_type: str
    imports: set[str] = field(default_factory=set)
    primary_key: bool = False
    nullable: bool = True
    unique: bool = False
    default: str | None = None
    autoincrement: bool = False
    fk_ref: str | None = None
    fk_table: str | None = None


@dataclass
class RelationshipDef:
    """A generated ORM relationship between two models."""

    attr_name: str
    target_class: str
    back_populates: str


@dataclass
class TableDef:
    """Parsed CREATE TABLE definition."""

    name: str
    columns: list[ColumnDef] = field(default_factory=list)
    relationships: list[RelationshipDef] = field(default_factory=list)


@dataclass
class EnumDef:
    """Parsed CREATE TYPE ... AS ENUM definition."""

    name: str
    values: list[str] = field(default_factory=list)
