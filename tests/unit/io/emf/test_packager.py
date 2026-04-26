"""Tests for the EMF relationship manager."""

from __future__ import annotations

from svg2ooxml.io.emf import EMFRelationshipManager


def test_register_generates_hash_filename() -> None:
    manager = EMFRelationshipManager()
    data = bytes.fromhex("DEADBEEF")

    entry, is_new = manager.register(data)

    assert is_new is True
    assert entry.filename.startswith("emf_")
    assert entry.filename.endswith(".emf")
    assert entry.relationship_id.startswith("rIdEmf")
    assert entry.data == data


def test_register_deduplicates_same_payload() -> None:
    manager = EMFRelationshipManager()
    data = bytes.fromhex("00" * 4)

    first, is_new_first = manager.register(data)
    second, is_new_second = manager.register(data)

    assert is_new_first is True
    assert is_new_second is False
    assert first is second


def test_register_updates_dimensions_on_duplicate() -> None:
    manager = EMFRelationshipManager()
    data = bytes.fromhex("11" * 4)

    entry, _ = manager.register(data)
    assert entry.width_emu is None

    updated_entry, is_new = manager.register(data, width_emu=42, height_emu=84)
    assert is_new is False
    assert updated_entry.width_emu == 42
    assert updated_entry.height_emu == 84


def test_register_prefers_supplied_relationship() -> None:
    manager = EMFRelationshipManager()
    data = bytes.fromhex("ABCD")

    entry, _ = manager.register(data, rel_id="rIdCustom")
    assert entry.relationship_id == "rIdCustom"


def test_register_rekeys_invalid_supplied_relationship() -> None:
    manager = EMFRelationshipManager()
    data = bytes.fromhex("ABCD")

    entry, _ = manager.register(data, rel_id='bad id" inject="1')

    assert entry.relationship_id.startswith("rIdEmf")
    assert entry.relationship_id != 'bad id" inject="1'


def test_register_stores_dimensions() -> None:
    manager = EMFRelationshipManager()
    data = bytes.fromhex("01020304")

    entry, is_new = manager.register(data, width_emu=1000, height_emu=2000)

    assert is_new is True
    assert entry.width_emu == 1000
    assert entry.height_emu == 2000
    assert entry.filename.endswith("_1000x2000.emf")
