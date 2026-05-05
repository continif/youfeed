"""Test puro per `category_service.to_tree` (non richiede DB)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.category_service import to_tree


def _cat(id_: int, *, name: str, parent_id: int | None, position: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        name=name,
        slug=name.lower(),
        parent_id=parent_id,
        position=position,
        color=None,
        is_public=True,
    )


def test_tree_root_only() -> None:
    cats = [_cat(1, name="Sport", parent_id=None), _cat(2, name="Tech", parent_id=None)]
    tree = to_tree(cats)
    assert len(tree) == 2
    assert all(node["children"] == [] for node in tree)


def test_tree_nested() -> None:
    cats = [
        _cat(1, name="Sport", parent_id=None),
        _cat(2, name="Calcio", parent_id=1),
        _cat(3, name="Serie A", parent_id=2),
        _cat(4, name="Tech", parent_id=None),
    ]
    tree = to_tree(cats)
    # 2 root: Sport e Tech
    assert len(tree) == 2
    sport = next(n for n in tree if n["name"] == "Sport")
    assert len(sport["children"]) == 1
    calcio = sport["children"][0]
    assert calcio["name"] == "Calcio"
    assert len(calcio["children"]) == 1
    assert calcio["children"][0]["name"] == "Serie A"


def test_tree_missing_parent_is_dropped() -> None:
    """Se un nodo punta a un parent_id non presente nella lista, finisce ignorato
    (non in root, non sotto nessun nodo). È accettabile: in pratica non succede
    perché query carica tutto sotto user_id."""
    cats = [
        _cat(1, name="Orphan", parent_id=999),
        _cat(2, name="Real", parent_id=None),
    ]
    tree = to_tree(cats)
    names = [n["name"] for n in tree]
    assert "Real" in names
    assert "Orphan" not in names
