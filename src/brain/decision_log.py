"""
Records LLM decisions + outcomes to JSONL for replay compilation and analysis.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DecisionRecord:
    timestamp: str
    type: str  # "strategic", "tactical", "stuck_recovery"
    model: str
    badges: int
    map_group: int
    map_num: int
    map_name: str
    position: tuple[int, int]
    decision: dict
    tokens_used: int
    latency_ms: float
    outcome: Optional[str] = None


class DecisionLog:
    """Logs all LLM decisions to JSONL file."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data_dir / "decisions.jsonl"
        self.token_path = self.data_dir / "token_usage.json"
        self._session_decisions: list[DecisionRecord] = []

    def log(self, record: DecisionRecord):
        self._session_decisions.append(record)
        entry = asdict(record)
        entry["position"] = list(entry["position"])
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write decision log: {e}")

        self._update_token_usage(record)

    def update_outcome(self, outcome: str):
        """Update the outcome of the most recent decision."""
        if not self._session_decisions:
            return
        self._session_decisions[-1].outcome = outcome
        update = {
            "type": "outcome_update",
            "timestamp": self._session_decisions[-1].timestamp,
            "outcome": outcome,
        }
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(update) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write outcome update: {e}")

    def _update_token_usage(self, record: DecisionRecord):
        """Update cumulative token usage file for DEKU monitoring."""
        try:
            if self.token_path.exists():
                usage = json.loads(self.token_path.read_text(encoding="utf-8"))
            else:
                usage = {
                    "total_tokens": 0,
                    "total_calls": 0,
                    "by_model": {},
                    "by_type": {},
                }
        except Exception:
            usage = {
                "total_tokens": 0,
                "total_calls": 0,
                "by_model": {},
                "by_type": {},
            }

        usage["total_tokens"] += record.tokens_used
        usage["total_calls"] += 1
        usage["last_call"] = record.timestamp

        model_key = (
            record.model.split("/")[-1] if "/" in record.model else record.model
        )
        usage.setdefault("by_model", {})[model_key] = (
            usage.get("by_model", {}).get(model_key, 0) + record.tokens_used
        )
        usage.setdefault("by_type", {})[record.type] = (
            usage.get("by_type", {}).get(record.type, 0) + record.tokens_used
        )

        try:
            self.token_path.write_text(
                json.dumps(usage, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to update token usage: {e}")

    def get_recent(self, n: int = 10) -> list[DecisionRecord]:
        return self._session_decisions[-n:]

    def get_session_stats(self) -> dict:
        total_tokens = sum(d.tokens_used for d in self._session_decisions)
        by_type: dict[str, int] = {}
        for d in self._session_decisions:
            by_type[d.type] = by_type.get(d.type, 0) + 1
        return {
            "total_decisions": len(self._session_decisions),
            "total_tokens": total_tokens,
            "by_type": by_type,
        }
