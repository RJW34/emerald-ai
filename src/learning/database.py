"""
Learning Database

Persistent storage for autonomous learning data using SQLite.
Stores:
- Coordinate discoveries
- Route attempts and outcomes
- Stuck events and recoveries
- Map obstacle data
- Successful action sequences
"""

import sqlite3
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator, Any

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "learning.db"


@dataclass
class CoordinateRecord:
    """A discovered coordinate mapping."""
    map_group: int
    map_num: int
    x: int
    y: int
    location_type: str  # "warp", "npc", "item", "obstacle", "path"
    description: str
    discovered_at: str
    verified: bool = False
    verification_count: int = 0


@dataclass
class RouteAttempt:
    """Record of a navigation attempt."""
    id: Optional[int]
    start_map: tuple[int, int]
    start_pos: tuple[int, int]
    target_map: tuple[int, int]
    target_pos: tuple[int, int]
    success: bool
    steps_taken: int
    time_elapsed: float
    path_taken: str  # JSON array of positions
    failure_reason: Optional[str]
    timestamp: str


@dataclass
class StuckRecord:
    """Record of a stuck event."""
    id: Optional[int]
    map_group: int
    map_num: int
    x: int
    y: int
    reason: str
    recovery_action: Optional[str]
    recovery_success: bool
    ticks_stuck: int
    timestamp: str


@dataclass
class ObservationRecord:
    """
    A gameplay observation recorded by the Player instance.

    Observations flow from Player -> database -> Scripter.
    The Scripter consumes observations to build automation scripts.
    """
    id: Optional[int]
    timestamp: str
    observation_type: str  # battle_started, warp_discovered, pokemon_caught, etc.
    map_group: int
    map_num: int
    x: int
    y: int
    game_state: str  # overworld, battle, menu, dialogue
    data: str  # JSON blob with type-specific data
    input_sequence: Optional[str] = None  # JSON array of inputs that led here
    consumed_by_scripter: bool = False
    created_at: Optional[str] = None


class LearningDatabase:
    """
    SQLite database for persistent learning storage.

    Usage:
        db = LearningDatabase()
        db.initialize()

        # Store a coordinate discovery
        db.store_coordinate(CoordinateRecord(...))

        # Query learned data
        warps = db.get_coordinates_by_type("warp", map_group=1, map_num=0)
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file (default: data/learning.db)
        """
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Coordinates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS coordinates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_group INTEGER NOT NULL,
                    map_num INTEGER NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    location_type TEXT NOT NULL,
                    description TEXT,
                    discovered_at TEXT NOT NULL,
                    verified INTEGER DEFAULT 0,
                    verification_count INTEGER DEFAULT 0,
                    UNIQUE(map_group, map_num, x, y, location_type)
                )
            """)

            # Route attempts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS route_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_map_group INTEGER NOT NULL,
                    start_map_num INTEGER NOT NULL,
                    start_x INTEGER NOT NULL,
                    start_y INTEGER NOT NULL,
                    target_map_group INTEGER NOT NULL,
                    target_map_num INTEGER NOT NULL,
                    target_x INTEGER NOT NULL,
                    target_y INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    steps_taken INTEGER NOT NULL,
                    time_elapsed REAL NOT NULL,
                    path_taken TEXT,
                    failure_reason TEXT,
                    timestamp TEXT NOT NULL
                )
            """)

            # Stuck events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stuck_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_group INTEGER NOT NULL,
                    map_num INTEGER NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    recovery_action TEXT,
                    recovery_success INTEGER DEFAULT 0,
                    ticks_stuck INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)

            # Obstacles table (learned impassable tiles)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS obstacles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_group INTEGER NOT NULL,
                    map_num INTEGER NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    obstacle_type TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    UNIQUE(map_group, map_num, x, y)
                )
            """)

            # Action sequences table (successful action patterns)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS action_sequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    context TEXT NOT NULL,
                    sequence TEXT NOT NULL,
                    success_count INTEGER DEFAULT 1,
                    failure_count INTEGER DEFAULT 0,
                    last_used TEXT NOT NULL,
                    UNIQUE(context, sequence)
                )
            """)

            # Observations table (Player -> Scripter data flow)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    observation_type TEXT NOT NULL,
                    map_group INTEGER NOT NULL,
                    map_num INTEGER NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    game_state TEXT NOT NULL,
                    data TEXT NOT NULL,
                    input_sequence TEXT,
                    consumed_by_scripter INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_coordinates_map
                ON coordinates(map_group, map_num)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_stuck_map
                ON stuck_events(map_group, map_num)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_obstacles_map
                ON obstacles(map_group, map_num)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_timestamp
                ON observations(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_type
                ON observations(observation_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_consumed
                ON observations(consumed_by_scripter)
            """)

            logger.info(f"Learning database initialized at {self.db_path}")

    # -------------------------------------------------------------------------
    # Coordinate Operations
    # -------------------------------------------------------------------------

    def store_coordinate(self, record: CoordinateRecord) -> int:
        """
        Store a discovered coordinate.

        Returns:
            ID of the inserted/updated record
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO coordinates
                (map_group, map_num, x, y, location_type, description,
                 discovered_at, verified, verification_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(map_group, map_num, x, y, location_type)
                DO UPDATE SET
                    verification_count = verification_count + 1,
                    verified = 1
            """, (
                record.map_group, record.map_num, record.x, record.y,
                record.location_type, record.description, record.discovered_at,
                record.verified, record.verification_count
            ))
            return cursor.lastrowid or 0

    def get_coordinate(self, map_group: int, map_num: int, x: int, y: int,
                       location_type: str) -> Optional[CoordinateRecord]:
        """Get a specific coordinate record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM coordinates
                WHERE map_group = ? AND map_num = ? AND x = ? AND y = ?
                AND location_type = ?
            """, (map_group, map_num, x, y, location_type))
            row = cursor.fetchone()
            if row:
                return CoordinateRecord(
                    map_group=row['map_group'],
                    map_num=row['map_num'],
                    x=row['x'],
                    y=row['y'],
                    location_type=row['location_type'],
                    description=row['description'],
                    discovered_at=row['discovered_at'],
                    verified=bool(row['verified']),
                    verification_count=row['verification_count']
                )
            return None

    def get_coordinates_by_type(self, location_type: str,
                                 map_group: Optional[int] = None,
                                 map_num: Optional[int] = None) -> list[CoordinateRecord]:
        """Get all coordinates of a specific type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM coordinates WHERE location_type = ?"
            params: list[Any] = [location_type]

            if map_group is not None:
                query += " AND map_group = ?"
                params.append(map_group)
            if map_num is not None:
                query += " AND map_num = ?"
                params.append(map_num)

            cursor.execute(query, params)

            return [
                CoordinateRecord(
                    map_group=row['map_group'],
                    map_num=row['map_num'],
                    x=row['x'],
                    y=row['y'],
                    location_type=row['location_type'],
                    description=row['description'],
                    discovered_at=row['discovered_at'],
                    verified=bool(row['verified']),
                    verification_count=row['verification_count']
                )
                for row in cursor.fetchall()
            ]

    def get_warps_for_map(self, map_group: int, map_num: int) -> list[CoordinateRecord]:
        """Get all known warps for a specific map."""
        return self.get_coordinates_by_type("warp", map_group, map_num)

    # -------------------------------------------------------------------------
    # Route Attempt Operations
    # -------------------------------------------------------------------------

    def store_route_attempt(self, attempt: RouteAttempt) -> int:
        """Store a route attempt record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO route_attempts
                (start_map_group, start_map_num, start_x, start_y,
                 target_map_group, target_map_num, target_x, target_y,
                 success, steps_taken, time_elapsed, path_taken,
                 failure_reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                attempt.start_map[0], attempt.start_map[1],
                attempt.start_pos[0], attempt.start_pos[1],
                attempt.target_map[0], attempt.target_map[1],
                attempt.target_pos[0], attempt.target_pos[1],
                attempt.success, attempt.steps_taken, attempt.time_elapsed,
                attempt.path_taken, attempt.failure_reason, attempt.timestamp
            ))
            return cursor.lastrowid or 0

    def get_successful_routes(self, start_map: tuple[int, int],
                               target_map: tuple[int, int]) -> list[RouteAttempt]:
        """Get successful routes between two maps."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM route_attempts
                WHERE start_map_group = ? AND start_map_num = ?
                AND target_map_group = ? AND target_map_num = ?
                AND success = 1
                ORDER BY steps_taken ASC
            """, (start_map[0], start_map[1], target_map[0], target_map[1]))

            return [self._row_to_route_attempt(row) for row in cursor.fetchall()]

    def _row_to_route_attempt(self, row: sqlite3.Row) -> RouteAttempt:
        """Convert database row to RouteAttempt."""
        return RouteAttempt(
            id=row['id'],
            start_map=(row['start_map_group'], row['start_map_num']),
            start_pos=(row['start_x'], row['start_y']),
            target_map=(row['target_map_group'], row['target_map_num']),
            target_pos=(row['target_x'], row['target_y']),
            success=bool(row['success']),
            steps_taken=row['steps_taken'],
            time_elapsed=row['time_elapsed'],
            path_taken=row['path_taken'],
            failure_reason=row['failure_reason'],
            timestamp=row['timestamp']
        )

    # -------------------------------------------------------------------------
    # Stuck Event Operations
    # -------------------------------------------------------------------------

    def store_stuck_event(self, record: StuckRecord) -> int:
        """Store a stuck event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stuck_events
                (map_group, map_num, x, y, reason, recovery_action,
                 recovery_success, ticks_stuck, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.map_group, record.map_num, record.x, record.y,
                record.reason, record.recovery_action, record.recovery_success,
                record.ticks_stuck, record.timestamp
            ))
            return cursor.lastrowid or 0

    def get_stuck_events_at_location(self, map_group: int, map_num: int,
                                      x: int, y: int) -> list[StuckRecord]:
        """Get stuck events that occurred at a specific location."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM stuck_events
                WHERE map_group = ? AND map_num = ? AND x = ? AND y = ?
                ORDER BY timestamp DESC
            """, (map_group, map_num, x, y))

            return [
                StuckRecord(
                    id=row['id'],
                    map_group=row['map_group'],
                    map_num=row['map_num'],
                    x=row['x'],
                    y=row['y'],
                    reason=row['reason'],
                    recovery_action=row['recovery_action'],
                    recovery_success=bool(row['recovery_success']),
                    ticks_stuck=row['ticks_stuck'],
                    timestamp=row['timestamp']
                )
                for row in cursor.fetchall()
            ]

    def get_successful_recovery_for_location(self, map_group: int, map_num: int,
                                              x: int, y: int,
                                              reason: str) -> Optional[str]:
        """Get a recovery action that worked at this location for this reason."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT recovery_action FROM stuck_events
                WHERE map_group = ? AND map_num = ? AND x = ? AND y = ?
                AND reason = ? AND recovery_success = 1
                ORDER BY timestamp DESC
                LIMIT 1
            """, (map_group, map_num, x, y, reason))
            row = cursor.fetchone()
            return row['recovery_action'] if row else None

    # -------------------------------------------------------------------------
    # Obstacle Operations
    # -------------------------------------------------------------------------

    def store_obstacle(self, map_group: int, map_num: int, x: int, y: int,
                       obstacle_type: str) -> int:
        """Store an obstacle/impassable tile."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO obstacles
                (map_group, map_num, x, y, obstacle_type, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (map_group, map_num, x, y, obstacle_type,
                  datetime.now().isoformat()))
            return cursor.lastrowid or 0

    def get_obstacles_for_map(self, map_group: int,
                               map_num: int) -> list[tuple[int, int, str]]:
        """Get all known obstacles for a map."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT x, y, obstacle_type FROM obstacles
                WHERE map_group = ? AND map_num = ?
            """, (map_group, map_num))
            return [(row['x'], row['y'], row['obstacle_type'])
                    for row in cursor.fetchall()]

    def is_obstacle(self, map_group: int, map_num: int, x: int, y: int) -> bool:
        """Check if a tile is a known obstacle."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM obstacles
                WHERE map_group = ? AND map_num = ? AND x = ? AND y = ?
            """, (map_group, map_num, x, y))
            return cursor.fetchone() is not None

    # -------------------------------------------------------------------------
    # Action Sequence Operations
    # -------------------------------------------------------------------------

    def store_action_sequence(self, context: str, sequence: list[str],
                               success: bool) -> None:
        """Store or update an action sequence."""
        sequence_json = json.dumps(sequence)
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if success:
                cursor.execute("""
                    INSERT INTO action_sequences (context, sequence, success_count,
                                                   failure_count, last_used)
                    VALUES (?, ?, 1, 0, ?)
                    ON CONFLICT(context, sequence) DO UPDATE SET
                        success_count = success_count + 1,
                        last_used = ?
                """, (context, sequence_json, datetime.now().isoformat(),
                      datetime.now().isoformat()))
            else:
                cursor.execute("""
                    INSERT INTO action_sequences (context, sequence, success_count,
                                                   failure_count, last_used)
                    VALUES (?, ?, 0, 1, ?)
                    ON CONFLICT(context, sequence) DO UPDATE SET
                        failure_count = failure_count + 1,
                        last_used = ?
                """, (context, sequence_json, datetime.now().isoformat(),
                      datetime.now().isoformat()))

    def get_best_action_sequence(self, context: str) -> Optional[list[str]]:
        """Get the most successful action sequence for a context."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sequence FROM action_sequences
                WHERE context = ? AND success_count > failure_count
                ORDER BY (success_count - failure_count) DESC
                LIMIT 1
            """, (context,))
            row = cursor.fetchone()
            if row:
                return json.loads(row['sequence'])
            return None

    # -------------------------------------------------------------------------
    # Observation Operations (Player -> Scripter data flow)
    # -------------------------------------------------------------------------

    def store_observation(self, record: ObservationRecord) -> int:
        """
        Store a gameplay observation from Player instance.

        Args:
            record: ObservationRecord to store

        Returns:
            ID of the inserted record
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO observations
                (timestamp, observation_type, map_group, map_num, x, y,
                 game_state, data, input_sequence, consumed_by_scripter, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.timestamp, record.observation_type,
                record.map_group, record.map_num, record.x, record.y,
                record.game_state, record.data, record.input_sequence,
                0, datetime.now().isoformat()
            ))
            return cursor.lastrowid or 0

    def get_unconsumed_observations(self, limit: int = 100) -> list[ObservationRecord]:
        """
        Get observations not yet consumed by Scripter.

        Args:
            limit: Maximum number of observations to return

        Returns:
            List of unconsumed ObservationRecords
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM observations
                WHERE consumed_by_scripter = 0
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))

            return [self._row_to_observation(row) for row in cursor.fetchall()]

    def mark_observations_consumed(self, observation_ids: list[int]) -> int:
        """
        Mark observations as consumed by Scripter.

        Args:
            observation_ids: List of observation IDs to mark

        Returns:
            Number of rows updated
        """
        if not observation_ids:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(observation_ids))
            cursor.execute(f"""
                UPDATE observations
                SET consumed_by_scripter = 1
                WHERE id IN ({placeholders})
            """, observation_ids)
            return cursor.rowcount

    def get_observations_by_type(self, observation_type: str,
                                  limit: int = 100) -> list[ObservationRecord]:
        """Get observations of a specific type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM observations
                WHERE observation_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (observation_type, limit))

            return [self._row_to_observation(row) for row in cursor.fetchall()]

    def get_recent_observations(self, limit: int = 50) -> list[ObservationRecord]:
        """Get most recent observations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM observations
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))

            return [self._row_to_observation(row) for row in cursor.fetchall()]

    def _row_to_observation(self, row: sqlite3.Row) -> ObservationRecord:
        """Convert database row to ObservationRecord."""
        return ObservationRecord(
            id=row['id'],
            timestamp=row['timestamp'],
            observation_type=row['observation_type'],
            map_group=row['map_group'],
            map_num=row['map_num'],
            x=row['x'],
            y=row['y'],
            game_state=row['game_state'],
            data=row['data'],
            input_sequence=row['input_sequence'],
            consumed_by_scripter=bool(row['consumed_by_scripter']),
            created_at=row['created_at']
        )

    def get_observation_count(self, consumed: Optional[bool] = None) -> int:
        """
        Get count of observations.

        Args:
            consumed: If specified, filter by consumed status

        Returns:
            Count of matching observations
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if consumed is None:
                cursor.execute("SELECT COUNT(*) FROM observations")
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM observations WHERE consumed_by_scripter = ?",
                    (1 if consumed else 0,)
                )
            return cursor.fetchone()[0]

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_statistics(self) -> dict[str, Any]:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            cursor.execute("SELECT COUNT(*) FROM coordinates")
            stats['coordinates'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM coordinates WHERE verified = 1")
            stats['verified_coordinates'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM route_attempts")
            stats['total_routes'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM route_attempts WHERE success = 1")
            stats['successful_routes'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stuck_events")
            stats['stuck_events'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM obstacles")
            stats['obstacles'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM observations")
            stats['observations'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM observations WHERE consumed_by_scripter = 0")
            stats['unconsumed_observations'] = cursor.fetchone()[0]

            return stats


# Singleton instance
_db_instance: Optional[LearningDatabase] = None


def get_database() -> LearningDatabase:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = LearningDatabase()
        _db_instance.initialize()
    return _db_instance
