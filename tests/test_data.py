"""Tests for move and species data modules."""

import pytest
from src.data.move_data import get_move_data, enrich_move, _MOVE_TABLE
from src.data.species_data import get_species_name, get_species_types, get_species_base_stats
from src.games.pokemon_gen3.data_types import Move, PokemonType


class TestMoveData:
    def test_known_move(self):
        move = get_move_data(89)  # Earthquake
        assert move.name == "Earthquake"
        assert move.type == PokemonType.GROUND
        assert move.power == 100
        assert move.accuracy == 100

    def test_stab_moves(self):
        surf = get_move_data(57)
        assert surf.name == "Surf"
        assert surf.type == PokemonType.WATER
        assert surf.power == 95

    def test_priority_move(self):
        quick = get_move_data(98)
        assert quick.name == "Quick Attack"
        assert quick.priority == 1

    def test_status_move(self):
        swords = get_move_data(14)
        assert swords.name == "Swords Dance"
        assert swords.power == 0

    def test_unknown_move(self):
        move = get_move_data(9999)
        assert "9999" in move.name
        assert move.pp == 5

    def test_enrich_preserves_pp(self):
        move = Move(id=53, pp=3)  # Flamethrower with 3 PP left
        enrich_move(move)
        assert move.name == "Flamethrower"
        assert move.power == 95
        assert move.pp == 3  # Preserved from memory
        assert move.max_pp == 15

    def test_contact_flag(self):
        tackle = get_move_data(33)
        assert tackle.is_contact
        surf = get_move_data(57)
        assert not surf.is_contact

    def test_move_table_coverage(self):
        """Verify we have data for commonly used moves."""
        important = [33, 52, 53, 55, 57, 58, 85, 89, 94, 157, 247, 280, 337, 348]
        for mid in important:
            assert mid in _MOVE_TABLE, f"Missing move {mid}"


class TestSpeciesData:
    def test_known_species(self):
        assert get_species_name(260) == "Swampert"
        assert get_species_name(257) == "Blaziken"

    def test_species_types(self):
        t1, t2 = get_species_types(260)
        assert t1 == PokemonType.WATER
        assert t2 == PokemonType.GROUND

    def test_single_type(self):
        t1, t2 = get_species_types(252)
        assert t1 == PokemonType.GRASS
        assert t2 is None

    def test_base_stats(self):
        stats = get_species_base_stats(376)  # Metagross
        assert stats["attack"] == 135
        assert stats["defense"] == 130

    def test_unknown_species(self):
        name = get_species_name(9999)
        assert "9999" in name

    def test_legendary_types(self):
        t1, t2 = get_species_types(384)  # Rayquaza
        assert t1 == PokemonType.DRAGON
        assert t2 == PokemonType.FLYING
