"""Schemi Pydantic per categorie."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Hex color, 6 cifre, opzionale
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class CategoryNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    parent_id: int | None
    position: int
    color: str | None
    is_public: bool
    children: list["CategoryNode"] = Field(default_factory=list)


CategoryNode.model_rebuild()


class CategoryCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    color: HexColor | None = None


class CategoryUpdateIn(BaseModel):
    """Tutti i campi opzionali: PATCH parziale.

    Per `parent_id` distinguiamo "non specificato" da "imposta a NULL" via
    sentinel: se la chiave è assente nel payload Pydantic ignora; per
    spostare a root l'utente passa esplicitamente `parent_id: null`.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: int | None = None
    color: HexColor | None = None
    position: int | None = None
    is_public: bool | None = None

    # Sentinel implementato dal router (vedi `model_fields_set`)


class CategoryTreeOut(BaseModel):
    tree: list[CategoryNode]


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    parent_id: int | None
    position: int
    color: str | None
    is_public: bool
