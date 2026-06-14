"""Async database layer supporting SQLite (WAL) and PostgreSQL."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from config import Config

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class GroupConfig:
    chat_id: int
    title: str
    is_authorized: bool
    moderation_enabled: bool
    strictness: str
    action_mode: str
    warning_threshold: int
    custom_rules: str


class Database:
    """Unified async database access layer."""

    def __init__(self) -> None:
        self._backend = Config.DB_BACKEND
        self._pool: Any = None
        self._conn: Any = None

    async def connect(self) -> None:
        if self._backend == "postgres":
            import asyncpg

            self._pool = await asyncpg.create_pool(Config.POSTGRES_DSN, min_size=1, max_size=10)
            async with self._pool.acquire() as conn:
                await self._init_schema_postgres(conn)
            logger.info("Connected to PostgreSQL")
            return

        import aiosqlite

        db_path = Config.DATABASE_URL.replace("sqlite:///", "")
        self._conn = await aiosqlite.connect(db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._init_schema_sqlite()
        await self._conn.commit()
        logger.info("Connected to SQLite at %s (WAL enabled)", db_path)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
        if self._conn:
            await self._conn.close()

    @asynccontextmanager
    async def _cursor(self) -> AsyncIterator[Any]:
        if self._backend == "postgres":
            async with self._pool.acquire() as conn:
                yield conn
        else:
            yield self._conn

    async def _execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        if self._backend == "postgres":
            pg_query = self._to_postgres_query(query)
            async with self._pool.acquire() as conn:
                await conn.execute(pg_query, *params)
            return
        await self._conn.execute(query, params)

    async def _executemany(self, query: str, params_list: list[tuple[Any, ...]]) -> None:
        if self._backend == "postgres":
            pg_query = self._to_postgres_query(query)
            async with self._pool.acquire() as conn:
                await conn.executemany(pg_query, params_list)
            return
        await self._conn.executemany(query, params_list)

    async def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        if self._backend == "postgres":
            pg_query = self._to_postgres_query(query)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(pg_query, *params)
                return dict(row) if row else None
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self._backend == "postgres":
            pg_query = self._to_postgres_query(query)
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(pg_query, *params)
                return [dict(r) for r in rows]
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def _commit(self) -> None:
        if self._backend != "postgres" and self._conn:
            await self._conn.commit()

    @staticmethod
    def _to_postgres_query(query: str) -> str:
        result = query
        index = 1
        while "?" in result:
            result = result.replace("?", f"${index}", 1)
            index += 1
        return result.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")

    async def _init_schema_sqlite(self) -> None:
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                is_super_admin INTEGER NOT NULL DEFAULT 0,
                is_banned_globally INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                is_authorized INTEGER NOT NULL DEFAULT 1,
                moderation_enabled INTEGER NOT NULL DEFAULT 1,
                strictness TEXT NOT NULL DEFAULT 'medium',
                action_mode TEXT NOT NULL DEFAULT 'delete_flag',
                warning_threshold INTEGER NOT NULL DEFAULT 3,
                custom_rules TEXT NOT NULL DEFAULT '',
                bot_is_admin INTEGER NOT NULL DEFAULT 0,
                messages_processed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                pattern TEXT NOT NULL,
                is_regex INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, pattern)
            );

            CREATE TABLE IF NOT EXISTS user_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                warning_count INTEGER NOT NULL DEFAULT 0,
                is_banned INTEGER NOT NULL DEFAULT 0,
                ban_reason TEXT,
                banned_at TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                message_text TEXT NOT NULL,
                classification TEXT NOT NULL,
                reason TEXT NOT NULL,
                layer TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cross_group_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_chat_id INTEGER NOT NULL,
                target_chat_id INTEGER,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_audit_chat ON audit_logs(chat_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_warnings_user ON user_warnings(user_id);
            CREATE INDEX IF NOT EXISTS idx_blacklist_chat ON group_blacklist(chat_id);
            """
        )

    async def _init_schema_postgres(self, conn: Any) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
                is_banned_globally BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS groups (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT UNIQUE NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                is_authorized BOOLEAN NOT NULL DEFAULT TRUE,
                moderation_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                strictness TEXT NOT NULL DEFAULT 'medium',
                action_mode TEXT NOT NULL DEFAULT 'delete_flag',
                warning_threshold INTEGER NOT NULL DEFAULT 3,
                custom_rules TEXT NOT NULL DEFAULT '',
                bot_is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                messages_processed INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS group_blacklist (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                pattern TEXT NOT NULL,
                is_regex BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE(chat_id, pattern)
            );
            CREATE TABLE IF NOT EXISTS user_warnings (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                warning_count INTEGER NOT NULL DEFAULT 0,
                is_banned BOOLEAN NOT NULL DEFAULT FALSE,
                ban_reason TEXT,
                banned_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL,
                UNIQUE(chat_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                username TEXT,
                message_text TEXT NOT NULL,
                classification TEXT NOT NULL,
                reason TEXT NOT NULL,
                layer TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cross_group_events (
                id SERIAL PRIMARY KEY,
                source_chat_id BIGINT NOT NULL,
                target_chat_id BIGINT,
                user_id BIGINT NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                notified BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS group_admins (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE(chat_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_audit_chat ON audit_logs(chat_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_warnings_user ON user_warnings(user_id);
            CREATE INDEX IF NOT EXISTS idx_blacklist_chat ON group_blacklist(chat_id);
            """
        )

    async def ensure_super_admin(self, telegram_id: int) -> None:
        now = utcnow().isoformat()
        existing = await self._fetchone(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if existing:
            await self._execute(
                "UPDATE users SET is_super_admin = 1 WHERE telegram_id = ?",
                (telegram_id,),
            )
        else:
            await self._execute(
                """
                INSERT INTO users (telegram_id, is_super_admin, created_at)
                VALUES (?, 1, ?)
                """,
                (telegram_id, now),
            )
        await self._commit()

    async def upsert_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> None:
        now = utcnow().isoformat()
        existing = await self._fetchone(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if existing:
            await self._execute(
                """
                UPDATE users SET username = ?, first_name = ?
                WHERE telegram_id = ?
                """,
                (username, first_name, telegram_id),
            )
        else:
            is_super = 1 if telegram_id == Config.SUPER_ADMIN_ID else 0
            await self._execute(
                """
                INSERT INTO users (telegram_id, username, first_name, is_super_admin, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (telegram_id, username, first_name, is_super, now),
            )
        await self._commit()

    async def is_super_admin(self, telegram_id: int) -> bool:
        if telegram_id == Config.SUPER_ADMIN_ID:
            return True
        row = await self._fetchone(
            "SELECT is_super_admin FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if self._backend == "postgres":
            return bool(row and row.get("is_super_admin"))
        return bool(row and row.get("is_super_admin"))

    async def is_globally_banned(self, telegram_id: int) -> bool:
        row = await self._fetchone(
            "SELECT is_banned_globally FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if self._backend == "postgres":
            return bool(row and row.get("is_banned_globally"))
        return bool(row and row.get("is_banned_globally"))

    async def set_global_ban(self, telegram_id: int, banned: bool) -> None:
        await self.upsert_user(telegram_id)
        await self._execute(
            "UPDATE users SET is_banned_globally = ? WHERE telegram_id = ?",
            (1 if banned else 0, telegram_id),
        )
        await self._commit()

    async def upsert_group(
        self,
        chat_id: int,
        title: str,
        bot_is_admin: bool = False,
    ) -> None:
        now = utcnow().isoformat()
        existing = await self._fetchone(
            "SELECT id FROM groups WHERE chat_id = ?",
            (chat_id,),
        )
        if existing:
            await self._execute(
                """
                UPDATE groups SET title = ?, bot_is_admin = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (title, 1 if bot_is_admin else 0, now, chat_id),
            )
        else:
            await self._execute(
                """
                INSERT INTO groups (
                    chat_id, title, bot_is_admin, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, title, 1 if bot_is_admin else 0, now, now),
            )
        await self._commit()

    async def set_group_authorized(self, chat_id: int, authorized: bool) -> None:
        await self._execute(
            "UPDATE groups SET is_authorized = ?, updated_at = ? WHERE chat_id = ?",
            (1 if authorized else 0, utcnow().isoformat(), chat_id),
        )
        await self._commit()

    async def get_group(self, chat_id: int) -> Optional[GroupConfig]:
        row = await self._fetchone("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        if not row:
            return None
        return GroupConfig(
            chat_id=row["chat_id"],
            title=row["title"],
            is_authorized=bool(row["is_authorized"]),
            moderation_enabled=bool(row["moderation_enabled"]),
            strictness=row["strictness"],
            action_mode=row["action_mode"],
            warning_threshold=row["warning_threshold"],
            custom_rules=row["custom_rules"] or "",
        )

    async def update_group_field(self, chat_id: int, field: str, value: Any) -> None:
        allowed = {
            "moderation_enabled",
            "strictness",
            "action_mode",
            "warning_threshold",
            "custom_rules",
            "is_authorized",
            "bot_is_admin",
        }
        if field not in allowed:
            raise ValueError(f"Invalid group field: {field}")
        await self._execute(
            f"UPDATE groups SET {field} = ?, updated_at = ? WHERE chat_id = ?",
            (value, utcnow().isoformat(), chat_id),
        )
        await self._commit()

    async def increment_messages_processed(self, chat_id: int) -> None:
        await self._execute(
            "UPDATE groups SET messages_processed = messages_processed + 1 WHERE chat_id = ?",
            (chat_id,),
        )
        await self._execute(
            """
            INSERT INTO stats (key, value) VALUES ('total_messages', 1)
            ON CONFLICT(key) DO UPDATE SET value = value + 1
            """,
        )
        await self._commit()

    async def get_blacklist(self, chat_id: int) -> list[dict[str, Any]]:
        return await self._fetchall(
            "SELECT pattern, is_regex FROM group_blacklist WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        )

    async def add_blacklist_pattern(
        self,
        chat_id: int,
        pattern: str,
        is_regex: bool = False,
    ) -> None:
        await self._execute(
            """
            INSERT INTO group_blacklist (chat_id, pattern, is_regex, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, pattern) DO NOTHING
            """,
            (chat_id, pattern, 1 if is_regex else 0, utcnow().isoformat()),
        )
        await self._commit()

    async def remove_blacklist_pattern(self, chat_id: int, pattern: str) -> None:
        await self._execute(
            "DELETE FROM group_blacklist WHERE chat_id = ? AND pattern = ?",
            (chat_id, pattern),
        )
        await self._commit()

    async def register_group_admin(self, chat_id: int, user_id: int) -> None:
        await self._execute(
            """
            INSERT INTO group_admins (chat_id, user_id, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO NOTHING
            """,
            (chat_id, user_id, utcnow().isoformat()),
        )
        await self._commit()

    async def get_group_admins(self, chat_id: int) -> list[int]:
        rows = await self._fetchall(
            "SELECT user_id FROM group_admins WHERE chat_id = ?",
            (chat_id,),
        )
        return [r["user_id"] for r in rows]

    async def get_warning_count(self, chat_id: int, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT warning_count FROM user_warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return row["warning_count"] if row else 0

    async def increment_warning(
        self,
        chat_id: int,
        user_id: int,
    ) -> tuple[int, bool]:
        now = utcnow().isoformat()
        row = await self._fetchone(
            "SELECT warning_count FROM user_warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        if row:
            new_count = row["warning_count"] + 1
            await self._execute(
                """
                UPDATE user_warnings SET warning_count = ?, updated_at = ?
                WHERE chat_id = ? AND user_id = ?
                """,
                (new_count, now, chat_id, user_id),
            )
        else:
            new_count = 1
            await self._execute(
                """
                INSERT INTO user_warnings (chat_id, user_id, warning_count, updated_at)
                VALUES (?, ?, 1, ?)
                """,
                (chat_id, user_id, now),
            )
        group = await self.get_group(chat_id)
        threshold = group.warning_threshold if group else 3
        should_ban = new_count >= threshold
        if should_ban:
            await self._execute(
                """
                UPDATE user_warnings SET is_banned = 1, ban_reason = ?, banned_at = ?
                WHERE chat_id = ? AND user_id = ?
                """,
                ("Warning threshold exceeded", now, chat_id, user_id),
            )
        await self._commit()
        return new_count, should_ban

    async def reset_warnings(self, chat_id: int, user_id: int) -> None:
        await self._execute(
            """
            UPDATE user_warnings SET warning_count = 0, is_banned = 0,
            ban_reason = NULL, banned_at = NULL, updated_at = ?
            WHERE chat_id = ? AND user_id = ?
            """,
            (utcnow().isoformat(), chat_id, user_id),
        )
        await self._commit()

    async def add_audit_log(
        self,
        chat_id: int,
        user_id: int,
        username: Optional[str],
        message_text: str,
        classification: str,
        reason: str,
        layer: str,
        action_taken: str,
    ) -> int:
        await self._execute(
            """
            INSERT INTO audit_logs (
                chat_id, user_id, username, message_text, classification,
                reason, layer, action_taken, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                user_id,
                username,
                message_text[:4000],
                classification,
                reason,
                layer,
                action_taken,
                utcnow().isoformat(),
            ),
        )
        await self._commit()
        if self._backend == "postgres":
            row = await self._fetchone(
                "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1",
            )
        else:
            row = await self._fetchone("SELECT last_insert_rowid() AS id")
        return row["id"] if row else 0

    async def get_audit_logs(self, chat_id: int, limit: int = 10) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT * FROM audit_logs WHERE chat_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (chat_id, limit),
        )

    async def get_global_audit_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._fetchall(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    async def add_cross_group_event(
        self,
        source_chat_id: int,
        user_id: int,
        event_type: str,
        reason: str,
        target_chat_id: Optional[int] = None,
    ) -> None:
        await self._execute(
            """
            INSERT INTO cross_group_events (
                source_chat_id, target_chat_id, user_id, event_type, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_chat_id,
                target_chat_id,
                user_id,
                event_type,
                reason,
                utcnow().isoformat(),
            ),
        )
        await self._commit()

    async def get_other_groups_for_user(self, user_id: int, exclude_chat_id: int) -> list[int]:
        rows = await self._fetchall(
            """
            SELECT DISTINCT chat_id FROM user_warnings
            WHERE user_id = ? AND chat_id != ?
            UNION
            SELECT DISTINCT chat_id FROM audit_logs
            WHERE user_id = ? AND chat_id != ?
            """,
            (user_id, exclude_chat_id, user_id, exclude_chat_id),
        )
        return [r["chat_id"] for r in rows]

    async def get_global_setting(self, key: str, default: str = "") -> str:
        row = await self._fetchone(
            "SELECT value FROM global_settings WHERE key = ?",
            (key,),
        )
        return row["value"] if row else default

    async def set_global_setting(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO global_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self._commit()

    async def get_ai_api_key(self) -> str:
        stored = await self.get_global_setting("ai_api_key")
        return stored or Config.AI_API_KEY

    async def set_ai_api_key(self, api_key: str) -> None:
        await self.set_global_setting("ai_api_key", api_key)

    async def get_global_stats(self) -> dict[str, Any]:
        groups = await self._fetchall(
            "SELECT chat_id, title, messages_processed FROM groups WHERE is_authorized = 1",
        )
        total_messages_row = await self._fetchone(
            "SELECT value FROM stats WHERE key = 'total_messages'",
        )
        admins = await self._fetchall(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM group_admins",
        )
        return {
            "active_groups": len(groups),
            "groups": groups,
            "total_messages": total_messages_row["value"] if total_messages_row else 0,
            "active_admins": admins[0]["cnt"] if admins else 0,
        }

    async def list_all_groups(self) -> list[dict[str, Any]]:
        return await self._fetchall("SELECT * FROM groups ORDER BY updated_at DESC")

    async def group_to_dict(self, chat_id: int) -> Optional[dict[str, Any]]:
        row = await self._fetchone("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        return row
