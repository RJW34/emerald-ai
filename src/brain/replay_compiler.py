"""
Compiles decision logs into Lua replay scripts.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ReplayCompiler:
    """Reads decision logs and outputs Lua replay scripts."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.decisions_path = self.data_dir / "decisions.jsonl"

    def compile(self, output_path: Optional[Path] = None) -> str:
        """Compile decision log into Lua replay script.

        Returns the Lua script as a string.
        """
        if not self.decisions_path.exists():
            logger.warning("No decisions.jsonl found")
            return "-- No decisions recorded\nreturn {}\n"

        decisions = self._read_decisions()
        lua_lines = self._decisions_to_lua(decisions)
        script = self._wrap_lua(lua_lines)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(script, encoding="utf-8")
            logger.info(f"Replay script written to {output_path}")

        return script

    def _read_decisions(self) -> list[dict]:
        decisions = []
        try:
            with self.decisions_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") != "outcome_update":
                            decisions.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to read decisions: {e}")
        return decisions

    def _decisions_to_lua(self, decisions: list[dict]) -> list[str]:
        lua_entries = []

        for d in decisions:
            dtype = d.get("type", "unknown")
            decision = d.get("decision", {})
            pos = d.get("position", [0, 0])
            map_group = d.get("map_group", 0)
            map_num = d.get("map_num", 0)

            if dtype == "strategic":
                objective = decision.get("objective", "unknown")
                destination = decision.get("destination", "unknown")
                lua_entries.append(
                    f"  {{type=\"strategic\", map={{{map_group},{map_num}}}, "
                    f"pos={{{pos[0]},{pos[1]}}}, "
                    f"objective=\"{self._escape_lua(objective)}\", "
                    f"destination=\"{self._escape_lua(destination)}\"}}"
                )

            elif dtype == "tactical":
                action = decision.get("action", "fight")
                move_index = decision.get("move_index", 0)
                lua_entries.append(
                    f"  {{type=\"battle\", map={{{map_group},{map_num}}}, "
                    f"action=\"{action}\", move_index={move_index}}}"
                )

            elif dtype == "stuck_recovery":
                action = decision.get("action", "A")
                lua_entries.append(
                    f"  {{type=\"recovery\", map={{{map_group},{map_num}}}, "
                    f"pos={{{pos[0]},{pos[1]}}}, "
                    f"action=\"{self._escape_lua(action)}\"}}"
                )

        return lua_entries

    def _wrap_lua(self, entries: list[str]) -> str:
        header = [
            "-- Auto-generated replay script from brain decisions",
            f"-- Compile time: {datetime.now().isoformat()}",
            "",
            "local replay = {",
        ]
        footer = [
            "}",
            "",
            "return replay",
        ]
        return "\n".join(header + entries + footer) + "\n"

    @staticmethod
    def _escape_lua(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
