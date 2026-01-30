"""
Battle Simulator — Run multi-turn battles with the AI offline.

Simulates damage application, fainting, and turn-by-turn combat
using the MockBizHawkClient. Lets you watch the AI fight through
complete battles and evaluate its decision quality.
"""

import logging
import struct
from typing import Optional

from .mock_client import MockBizHawkClient, MockBattlePokemon, SCENARIOS
from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector
from ..games.pokemon_gen3.battle_handler import PokemonGen3BattleHandler, BattleAction
from ..games.pokemon_gen3.memory_map import PokemonGen3Memory as Mem
from ..ai.battle_ai import BattleAI, BattleContext, BattleStrategy
from ..data.move_data import get_move_data
from ..data.species_data import get_species_name

logger = logging.getLogger(__name__)


class BattleSimulator:
    """
    Simulates multi-turn Pokemon battles using the AI.
    
    After each AI decision, applies simplified damage to the mock memory
    and lets the AI decide again. Tracks the battle log.
    """
    
    def __init__(self, scenario_name: str, strategy: str = "aggressive"):
        self.client = MockBizHawkClient(scenario_name)
        self.client.connect()
        self.scenario = SCENARIOS[scenario_name]
        
        self.detector = PokemonGen3StateDetector(self.client)
        self.handler = PokemonGen3BattleHandler(self.client)
        self.ai = BattleAI(self.handler)
        
        strat_map = {
            "aggressive": BattleStrategy.AGGRESSIVE,
            "safe": BattleStrategy.SAFE,
            "speedrun": BattleStrategy.SPEEDRUN,
            "grind": BattleStrategy.GRIND,
            "catch": BattleStrategy.CATCH,
        }
        self.ai.set_strategy(strat_map.get(strategy, BattleStrategy.AGGRESSIVE))
        
        self.log: list[str] = []
        self.turns = 0
        self.max_turns = 50
        self.result: Optional[str] = None  # "win", "lose", "flee"
    
    def run(self) -> str:
        """
        Run the full battle simulation.
        
        Returns:
            "win", "lose", or "flee"
        """
        self._log(f"=== Battle Start: {self.scenario['description']} ===")
        
        # Initial state read
        self.detector.refresh_pointers()
        battle_state = self.handler.read_battle_state()
        
        player = battle_state.player_lead
        enemy = battle_state.enemy_lead
        if player and enemy:
            self._log(f"Player: {get_species_name(player.species_id)} Lv.{player.level} "
                      f"HP:{player.hp}/{player.max_hp}")
            self._log(f"Enemy:  {get_species_name(enemy.species_id)} Lv.{enemy.level} "
                      f"HP:{enemy.hp}/{enemy.max_hp}")
            self._log("")
        
        while self.turns < self.max_turns:
            self.turns += 1
            
            # Re-read state
            battle_state = self.handler.read_battle_state()
            player = battle_state.player_lead
            enemy = battle_state.enemy_lead
            
            if not player or not enemy:
                self._log("ERROR: Can't read battle Pokemon")
                break
            
            # Check for fainted
            if player.hp <= 0:
                self.result = "lose"
                self._log(f"Turn {self.turns}: {player.species_name} fainted! LOSS")
                break
            if enemy.hp <= 0:
                self.result = "win"
                self._log(f"Turn {self.turns}: {enemy.species_name} fainted! WIN")
                break
            
            # AI decides
            party = self.detector.read_party()
            ctx = BattleContext(
                state=battle_state,
                party=party,
                turns_in_battle=self.turns - 1,
            )
            decision = self.ai.decide(ctx)
            
            # Log decision
            if decision.action == BattleAction.RUN:
                self.result = "flee"
                self._log(f"Turn {self.turns}: Fled the battle!")
                break
            elif decision.action == BattleAction.FIGHT:
                if decision.move_index < len(player.moves):
                    move = player.moves[decision.move_index]
                    self._log(f"Turn {self.turns}: {player.species_name} uses {move.name}!")
                    
                    # Apply damage
                    if move.power > 0:
                        min_dmg, max_dmg = self.handler.estimate_damage(
                            move, player, enemy, battle_state.weather
                        )
                        # Use average damage
                        dmg = (min_dmg + max_dmg) // 2
                        new_hp = max(0, enemy.hp - dmg)
                        self._log(f"  → Deals {dmg} damage! Enemy HP: {enemy.hp} → {new_hp}")
                        self._apply_enemy_damage(dmg)
                    else:
                        self._log(f"  → (status move)")
                    
                    # Deduct PP
                    self._deduct_pp(0, decision.move_index)
                else:
                    self._log(f"Turn {self.turns}: Invalid move index {decision.move_index}")
            elif decision.action == BattleAction.SWITCH:
                self._log(f"Turn {self.turns}: Switch to Pokemon #{decision.pokemon_index}")
            
            # Simple enemy attack (uses first damaging move)
            if enemy.hp > 0:
                enemy_move = None
                for m in enemy.moves:
                    if m.power > 0 and m.pp > 0:
                        enemy_move = m
                        break
                
                if enemy_move:
                    min_dmg, max_dmg = self.handler.estimate_damage(
                        enemy_move, enemy, player, battle_state.weather
                    )
                    dmg = (min_dmg + max_dmg) // 2
                    new_hp = max(0, player.hp - dmg)
                    self._log(f"  Enemy {enemy.species_name} uses {enemy_move.name}! "
                              f"Deals {dmg}. Player HP: {player.hp} → {new_hp}")
                    self._apply_player_damage(dmg)
        
        if self.result is None:
            self.result = "timeout"
            self._log(f"Battle timed out after {self.max_turns} turns")
        
        self._log(f"\n=== Battle Result: {self.result.upper()} in {self.turns} turns ===")
        return self.result
    
    def _apply_enemy_damage(self, damage: int):
        """Apply damage to enemy Pokemon in mock memory."""
        # Enemy is battler index 1, HP at offset 0x28
        addr_offset = 88 + 0x28  # battler 1 offset + HP offset
        current_hp = struct.unpack_from('<H', self.client._battle_mon_data, addr_offset)[0]
        new_hp = max(0, current_hp - damage)
        struct.pack_into('<H', self.client._battle_mon_data, addr_offset, new_hp)
    
    def _apply_player_damage(self, damage: int):
        """Apply damage to player Pokemon in mock memory."""
        addr_offset = 0x28  # battler 0, HP offset
        current_hp = struct.unpack_from('<H', self.client._battle_mon_data, addr_offset)[0]
        new_hp = max(0, current_hp - damage)
        struct.pack_into('<H', self.client._battle_mon_data, addr_offset, new_hp)
    
    def _deduct_pp(self, battler: int, move_index: int):
        """Deduct 1 PP from a move."""
        addr_offset = (battler * 88) + 0x24 + move_index
        current_pp = self.client._battle_mon_data[addr_offset]
        if current_pp > 0:
            self.client._battle_mon_data[addr_offset] = current_pp - 1
    
    def _log(self, msg: str):
        self.log.append(msg)
        logger.info(msg)
    
    def print_log(self):
        for line in self.log:
            print(line)


def run_all_scenarios():
    """Run all battle scenarios and print results."""
    print("=" * 60)
    print("EMERALD AI BATTLE SIMULATOR")
    print("=" * 60)
    
    for name in SCENARIOS:
        print()
        sim = BattleSimulator(name)
        result = sim.run()
        sim.print_log()
        print()
    
    print("=" * 60)
    print("All scenarios complete!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_all_scenarios()
