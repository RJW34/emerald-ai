#!/usr/bin/env python3
"""
Test script for Options menu memory reading and verification.

Usage:
    1. Start BizHawk with Pokemon Emerald and run the Lua script
    2. Load a save file (so pointers are valid)
    3. Run: python test_options.py
    
This will:
- Connect to BizHawk
- Read current options settings
- Display settings in human-readable format
- Report if settings are optimal for AI play
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.emulator.bizhawk_client import BizHawkClient
from src.games.pokemon_gen3.state_detector import PokemonGen3StateDetector
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("Pokemon Emerald - Options Memory Test")
    logger.info("=" * 60)
    
    # Connect to BizHawk
    client = BizHawkClient()
    if not client.connect():
        logger.error("Failed to connect to BizHawk")
        logger.error("Make sure BizHawk is running with the Lua script")
        return 1
    
    logger.info(f"Connected to: {client.get_game_title()} ({client.get_game_code()})")
    
    # Create state detector
    detector = PokemonGen3StateDetector(client)
    
    # Refresh pointers
    if not detector.refresh_pointers():
        logger.error("Failed to refresh pointers - is a save file loaded?")
        return 1
    
    logger.info("Pointers valid - reading options...")
    logger.info("")
    
    # Read options
    options = detector.read_options()
    
    # Display current settings
    logger.info("CURRENT SETTINGS:")
    logger.info("-" * 60)
    
    # Text Speed
    text_speed_names = {0: "Slow", 1: "Mid", 2: "Fast"}
    text_speed = options['text_speed']
    text_speed_str = text_speed_names.get(text_speed, f"Unknown({text_speed})")
    logger.info(f"  Text Speed:    {text_speed_str} (value: {text_speed})")
    
    # Battle Scene
    battle_scene_names = {0: "On", 1: "Off"}
    battle_scene = options['battle_scene']
    battle_scene_str = battle_scene_names.get(battle_scene, f"Unknown({battle_scene})")
    logger.info(f"  Battle Scene:  {battle_scene_str} (value: {battle_scene})")
    
    # Battle Style
    battle_style_names = {0: "Switch", 1: "Set"}
    battle_style = options['battle_style']
    battle_style_str = battle_style_names.get(battle_style, f"Unknown({battle_style})")
    logger.info(f"  Battle Style:  {battle_style_str} (value: {battle_style})")
    
    # Sound
    sound_names = {0: "Mono", 1: "Stereo"}
    sound = options['sound']
    sound_str = sound_names.get(sound, f"Unknown({sound})")
    logger.info(f"  Sound:         {sound_str} (value: {sound})")
    
    logger.info(f"  Raw byte:      0x{options['raw']:02X} ({options['raw']})")
    logger.info("")
    
    # Check if optimal
    logger.info("OPTIMAL SETTINGS CHECK:")
    logger.info("-" * 60)
    logger.info("  Target: Text Speed=Fast, Battle Scene=Off, Battle Style=Set")
    logger.info("")
    
    is_optimal = detector.verify_optimal_settings()
    
    if is_optimal:
        logger.info("  ✓ PASS - All settings are optimal!")
    else:
        logger.info("  ✗ FAIL - Settings need configuration:")
        if text_speed != 2:
            logger.info(f"    - Text Speed is {text_speed_str}, should be Fast")
        if battle_scene != 1:
            logger.info(f"    - Battle Scene is {battle_scene_str}, should be Off")
        if battle_style != 1:
            logger.info(f"    - Battle Style is {battle_style_str}, should be Set")
    
    logger.info("")
    logger.info("=" * 60)
    
    client.close()
    return 0 if is_optimal else 1


if __name__ == "__main__":
    sys.exit(main())
