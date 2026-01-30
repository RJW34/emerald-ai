"""Tests for the multi-turn battle simulator."""

from src.emulator.battle_simulator import BattleSimulator


class TestBattleSimulator:
    def test_mudkip_wins(self):
        sim = BattleSimulator("mudkip_vs_poochyena")
        result = sim.run()
        assert result == "win"
        assert sim.turns <= 5

    def test_swampert_wins(self):
        sim = BattleSimulator("swampert_vs_wailord_rain")
        result = sim.run()
        assert result == "win"

    def test_speedrun_flees_wild(self):
        sim = BattleSimulator("mudkip_vs_poochyena", strategy="speedrun")
        result = sim.run()
        assert result == "flee"
        assert sim.turns == 1

    def test_battle_log_populated(self):
        sim = BattleSimulator("mudkip_vs_poochyena")
        sim.run()
        assert len(sim.log) > 3
        assert "Mudkip" in sim.log[1]
        assert "Poochyena" in sim.log[2]

    def test_no_water_moves_on_water_absorb(self):
        sim = BattleSimulator("swampert_vs_wailord_rain")
        sim.run()
        # Check the log never shows Surf being used by player
        player_moves = [l for l in sim.log if "Swampert uses" in l]
        for move_line in player_moves:
            assert "Surf" not in move_line, f"AI used Surf against Water Absorb: {move_line}"

    def test_pp_deducted(self):
        sim = BattleSimulator("mudkip_vs_poochyena")
        sim.run()
        # Tackle starts at 35 PP, should be reduced
        pp_after = sim.client._battle_mon_data[0x24]  # PP of first move
        assert pp_after < 35
