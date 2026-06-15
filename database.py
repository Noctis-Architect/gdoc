"""Async database layer supporting SQLite (WAL) and PostgreSQL."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    suspect_rules: str
    enabled_templates: str = ""
    link_policy: str = "allow_all"


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
                await self._migrate_schema_postgres(conn)
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
        await self._migrate_schema_sqlite()
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
                action_mode TEXT NOT NULL DEFAULT 'keep_alert',
                warning_threshold INTEGER NOT NULL DEFAULT 3,
                custom_rules TEXT NOT NULL DEFAULT '',
                suspect_rules TEXT NOT NULL DEFAULT '',
                enabled_templates TEXT NOT NULL DEFAULT '',
                link_policy TEXT NOT NULL DEFAULT 'allow_all',
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
                message_id INTEGER,
                review_status TEXT NOT NULL DEFAULT 'auto',
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

            CREATE TABLE IF NOT EXISTS group_message_daily (
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, day)
            );

            CREATE INDEX IF NOT EXISTS idx_audit_chat ON audit_logs(chat_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_warnings_user ON user_warnings(user_id);
            CREATE INDEX IF NOT EXISTS idx_blacklist_chat ON group_blacklist(chat_id);

            CREATE TABLE IF NOT EXISTS group_link_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, domain)
            );

            CREATE INDEX IF NOT EXISTS idx_link_domains_chat ON group_link_domains(chat_id);
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
                action_mode TEXT NOT NULL DEFAULT 'keep_alert',
                warning_threshold INTEGER NOT NULL DEFAULT 3,
                custom_rules TEXT NOT NULL DEFAULT '',
                suspect_rules TEXT NOT NULL DEFAULT '',
                enabled_templates TEXT NOT NULL DEFAULT '',
                link_policy TEXT NOT NULL DEFAULT 'allow_all',
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
                message_id BIGINT,
                review_status TEXT NOT NULL DEFAULT 'auto',
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
            CREATE TABLE IF NOT EXISTS group_message_daily (
                chat_id BIGINT NOT NULL,
                day DATE NOT NULL,
                count BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, day)
            );
            CREATE INDEX IF NOT EXISTS idx_audit_chat ON audit_logs(chat_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_warnings_user ON user_warnings(user_id);
            CREATE INDEX IF NOT EXISTS idx_blacklist_chat ON group_blacklist(chat_id);
            CREATE TABLE IF NOT EXISTS group_link_domains (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                domain TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE(chat_id, domain)
            );
            CREATE INDEX IF NOT EXISTS idx_link_domains_chat ON group_link_domains(chat_id);
            """
        )

    async def _migrate_schema_sqlite(self) -> None:
        cols = await self._fetchall("PRAGMA table_info(users)")
        col_names = {c["name"] for c in cols}
        if "subscription_started_at" not in col_names:
            await self._conn.execute(
                "ALTER TABLE users ADD COLUMN subscription_started_at TEXT",
            )
        if "subscription_expires_at" not in col_names:
            await self._conn.execute(
                "ALTER TABLE users ADD COLUMN subscription_expires_at TEXT",
            )

        audit_cols = await self._fetchall("PRAGMA table_info(audit_logs)")
        audit_names = {c["name"] for c in audit_cols}
        if "message_id" not in audit_names:
            await self._conn.execute(
                "ALTER TABLE audit_logs ADD COLUMN message_id INTEGER",
            )
        if "review_status" not in audit_names:
            await self._conn.execute(
                "ALTER TABLE audit_logs ADD COLUMN review_status TEXT NOT NULL DEFAULT 'auto'",
            )

        group_cols = await self._fetchall("PRAGMA table_info(groups)")
        group_names = {c["name"] for c in group_cols}
        if "suspect_rules" not in group_names:
            await self._conn.execute(
                "ALTER TABLE groups ADD COLUMN suspect_rules TEXT NOT NULL DEFAULT ''",
            )
        if "enabled_templates" not in group_names:
            await self._conn.execute(
                "ALTER TABLE groups ADD COLUMN enabled_templates TEXT NOT NULL DEFAULT ''",
            )
        if "link_policy" not in group_names:
            await self._conn.execute(
                "ALTER TABLE groups ADD COLUMN link_policy TEXT NOT NULL DEFAULT 'allow_all'",
            )

        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_link_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, domain)
            )
            """,
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_link_domains_chat ON group_link_domains(chat_id)",
        )

    async def _migrate_schema_postgres(self, conn: Any) -> None:
        await conn.execute(
            """
            ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_started_at TIMESTAMPTZ;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;
            ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS message_id BIGINT;
            ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'auto';
            ALTER TABLE groups ADD COLUMN IF NOT EXISTS suspect_rules TEXT NOT NULL DEFAULT '';
            ALTER TABLE groups ADD COLUMN IF NOT EXISTS enabled_templates TEXT NOT NULL DEFAULT '';
            ALTER TABLE groups ADD COLUMN IF NOT EXISTS link_policy TEXT NOT NULL DEFAULT 'allow_all';
            CREATE TABLE IF NOT EXISTS group_link_domains (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                domain TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE(chat_id, domain)
            );
            CREATE INDEX IF NOT EXISTS idx_link_domains_chat ON group_link_domains(chat_id);
            """,
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

    async def start_admin_trial(self, telegram_id: int) -> None:
        """Start the free trial for a non-super-admin on first /start."""
        if telegram_id == Config.SUPER_ADMIN_ID:
            return
        row = await self._fetchone(
            "SELECT subscription_started_at FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if row and row.get("subscription_started_at"):
            return
        now = utcnow()
        expires = now + timedelta(days=Config.ADMIN_TRIAL_DAYS)
        if row:
            await self._execute(
                """
                UPDATE users SET subscription_started_at = ?, subscription_expires_at = ?
                WHERE telegram_id = ?
                """,
                (now.isoformat(), expires.isoformat(), telegram_id),
            )
        else:
            await self._execute(
                """
                INSERT INTO users (
                    telegram_id, is_super_admin, created_at,
                    subscription_started_at, subscription_expires_at
                ) VALUES (?, 0, ?, ?, ?)
                """,
                (telegram_id, now.isoformat(), now.isoformat(), expires.isoformat()),
            )
        await self._commit()

    async def is_admin_subscription_active(self, telegram_id: int) -> bool:
        if telegram_id == Config.SUPER_ADMIN_ID:
            return True
        if await self.is_super_admin(telegram_id):
            return True
        row = await self._fetchone(
            "SELECT subscription_expires_at FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if not row or not row.get("subscription_expires_at"):
            return False
        expires = datetime.fromisoformat(row["subscription_expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > utcnow()

    async def get_admin_subscription(self, telegram_id: int) -> Optional[dict[str, Any]]:
        return await self._fetchone(
            """
            SELECT telegram_id, username, first_name, subscription_started_at,
                   subscription_expires_at, is_super_admin
            FROM users WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

    async def extend_admin_subscription(self, telegram_id: int, days: int | None = None) -> datetime:
        trial_days = days if days is not None else Config.ADMIN_TRIAL_DAYS
        await self.upsert_user(telegram_id)
        row = await self._fetchone(
            "SELECT subscription_expires_at FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        now = utcnow()
        current_expires = None
        if row and row.get("subscription_expires_at"):
            current_expires = datetime.fromisoformat(row["subscription_expires_at"])
            if current_expires.tzinfo is None:
                current_expires = current_expires.replace(tzinfo=timezone.utc)
        base = current_expires if current_expires and current_expires > now else now
        new_expires = base + timedelta(days=trial_days)
        await self._execute(
            """
            UPDATE users SET subscription_expires_at = ?,
            subscription_started_at = COALESCE(subscription_started_at, ?)
            WHERE telegram_id = ?
            """,
            (new_expires.isoformat(), now.isoformat(), telegram_id),
        )
        await self._commit()
        return new_expires

    async def list_registered_admins(self) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT u.telegram_id, u.username, u.first_name,
                   u.subscription_started_at, u.subscription_expires_at,
                   u.is_super_admin,
                   (
                       SELECT COUNT(DISTINCT ga.chat_id)
                       FROM group_admins ga WHERE ga.user_id = u.telegram_id
                   ) AS group_count
            FROM users u
            WHERE EXISTS (
                SELECT 1 FROM group_admins ga WHERE ga.user_id = u.telegram_id
            )
            ORDER BY u.subscription_expires_at ASC
            """,
        )

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
            suspect_rules=row.get("suspect_rules") or "",
            enabled_templates=row.get("enabled_templates") or "",
            link_policy=row.get("link_policy") or "allow_all",
        )

    async def update_group_field(self, chat_id: int, field: str, value: Any) -> None:
        allowed = {
            "moderation_enabled",
            "strictness",
            "action_mode",
            "warning_threshold",
            "custom_rules",
            "suspect_rules",
            "enabled_templates",
            "link_policy",
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
        today = utcnow().strftime("%Y-%m-%d")
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
        await self._execute(
            """
            INSERT INTO group_message_daily (chat_id, day, count) VALUES (?, ?, 1)
            ON CONFLICT(chat_id, day) DO UPDATE SET count = count + 1
            """,
            (chat_id, today),
        )
        await self._commit()

    async def get_group_message_stats(self, chat_id: int) -> dict[str, int]:
        now = utcnow()
        week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        month_start = (now - timedelta(days=29)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")

        week_row = await self._fetchone(
            """
            SELECT COALESCE(SUM(count), 0) AS total FROM group_message_daily
            WHERE chat_id = ? AND day >= ? AND day <= ?
            """,
            (chat_id, week_start, today),
        )
        month_row = await self._fetchone(
            """
            SELECT COALESCE(SUM(count), 0) AS total FROM group_message_daily
            WHERE chat_id = ? AND day >= ? AND day <= ?
            """,
            (chat_id, month_start, today),
        )
        group = await self._fetchone(
            "SELECT messages_processed FROM groups WHERE chat_id = ?",
            (chat_id,),
        )
        return {
            "week": int(week_row["total"]) if week_row else 0,
            "month": int(month_row["total"]) if month_row else 0,
            "total": int(group["messages_processed"]) if group else 0,
        }

    async def get_groups_message_stats_bulk(self, chat_ids: list[int]) -> dict[int, dict[str, int]]:
        if not chat_ids:
            return {}
        now = utcnow()
        week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        month_start = (now - timedelta(days=29)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")
        placeholders = ",".join("?" * len(chat_ids))
        params = tuple(chat_ids) + (week_start, today)
        week_rows = await self._fetchall(
            f"""
            SELECT chat_id, COALESCE(SUM(count), 0) AS total FROM group_message_daily
            WHERE chat_id IN ({placeholders}) AND day >= ? AND day <= ?
            GROUP BY chat_id
            """,
            params,
        )
        month_params = tuple(chat_ids) + (month_start, today)
        month_rows = await self._fetchall(
            f"""
            SELECT chat_id, COALESCE(SUM(count), 0) AS total FROM group_message_daily
            WHERE chat_id IN ({placeholders}) AND day >= ? AND day <= ?
            GROUP BY chat_id
            """,
            month_params,
        )
        week_map = {r["chat_id"]: int(r["total"]) for r in week_rows}
        month_map = {r["chat_id"]: int(r["total"]) for r in month_rows}
        result: dict[int, dict[str, int]] = {}
        for cid in chat_ids:
            result[cid] = {
                "week": week_map.get(cid, 0),
                "month": month_map.get(cid, 0),
            }
        return result

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

    async def get_link_domains(self, chat_id: int) -> list[str]:
        rows = await self._fetchall(
            "SELECT domain FROM group_link_domains WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        )
        return [r["domain"] for r in rows]

    async def add_link_domain(self, chat_id: int, domain: str) -> None:
        await self._execute(
            """
            INSERT INTO group_link_domains (chat_id, domain, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, domain) DO NOTHING
            """,
            (chat_id, domain, utcnow().isoformat()),
        )
        await self._commit()

    async def remove_link_domain(self, chat_id: int, domain: str) -> None:
        await self._execute(
            "DELETE FROM group_link_domains WHERE chat_id = ? AND domain = ?",
            (chat_id, domain),
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

    async def set_group_ban(
        self,
        chat_id: int,
        user_id: int,
        banned: bool,
        reason: str | None = None,
    ) -> None:
        now = utcnow().isoformat()
        row = await self._fetchone(
            "SELECT id FROM user_warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        if row:
            if banned:
                await self._execute(
                    """
                    UPDATE user_warnings SET is_banned = 1, ban_reason = ?,
                    banned_at = ?, updated_at = ?
                    WHERE chat_id = ? AND user_id = ?
                    """,
                    (reason or "Banned", now, now, chat_id, user_id),
                )
            else:
                await self._execute(
                    """
                    UPDATE user_warnings SET is_banned = 0, ban_reason = NULL,
                    banned_at = NULL, updated_at = ?
                    WHERE chat_id = ? AND user_id = ?
                    """,
                    (now, chat_id, user_id),
                )
        elif banned:
            await self._execute(
                """
                INSERT INTO user_warnings (
                    chat_id, user_id, warning_count, is_banned, ban_reason, banned_at, updated_at
                ) VALUES (?, ?, 0, 1, ?, ?, ?)
                """,
                (chat_id, user_id, reason or "Banned", now, now),
            )
        await self._commit()

    async def list_group_banned_users(
        self,
        chat_id: int,
        limit: int = 15,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT uw.user_id, uw.ban_reason, uw.banned_at, uw.warning_count,
                   u.username, u.first_name
            FROM user_warnings uw
            LEFT JOIN users u ON u.telegram_id = uw.user_id
            WHERE uw.chat_id = ? AND uw.is_banned = 1
            ORDER BY uw.banned_at DESC
            LIMIT ? OFFSET ?
            """,
            (chat_id, limit, offset),
        )

    async def count_group_banned_users(self, chat_id: int) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS cnt FROM user_warnings WHERE chat_id = ? AND is_banned = 1",
            (chat_id,),
        )
        return int(row["cnt"]) if row else 0

    async def list_globally_banned_users(self, limit: int = 30) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT telegram_id, username, first_name, created_at
            FROM users WHERE is_banned_globally = 1
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        )

    async def get_user_warnings_row(
        self,
        chat_id: int,
        user_id: int,
    ) -> Optional[dict[str, Any]]:
        return await self._fetchone(
            "SELECT * FROM user_warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )

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
        *,
        message_id: Optional[int] = None,
        review_status: str = "auto",
    ) -> int:
        await self._execute(
            """
            INSERT INTO audit_logs (
                chat_id, user_id, username, message_text, classification,
                reason, layer, action_taken, message_id, review_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                message_id,
                review_status,
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

    async def get_audit_log(self, audit_id: int) -> Optional[dict[str, Any]]:
        return await self._fetchone(
            "SELECT * FROM audit_logs WHERE id = ?",
            (audit_id,),
        )

    async def update_audit_review_status(self, audit_id: int, status: str) -> None:
        await self._execute(
            "UPDATE audit_logs SET review_status = ? WHERE id = ?",
            (status, audit_id),
        )
        await self._commit()

    async def get_audit_logs(self, chat_id: int, limit: int = 10) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT * FROM audit_logs WHERE chat_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (chat_id, limit),
        )

    async def get_user_violation_reasons(
        self,
        chat_id: int,
        user_id: int,
        limit: int = 5,
    ) -> list[str]:
        rows = await self._fetchall(
            """
            SELECT reason FROM audit_logs
            WHERE chat_id = ? AND user_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (chat_id, user_id, limit),
        )
        return [r["reason"] for r in rows if r.get("reason")]

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

    async def get_ai_provider(self) -> str:
        return await self.get_global_setting("ai_provider", Config.AI_PROVIDER)

    async def set_ai_provider(self, provider: str) -> None:
        await self.set_global_setting("ai_provider", provider.lower())

    async def get_ai_model(self) -> str:
        return await self.get_global_setting("ai_model", Config.AI_MODEL)

    async def set_ai_model(self, model: str) -> None:
        await self.set_global_setting("ai_model", model)

    async def get_ai_base_url(self) -> str:
        return await self.get_global_setting("ai_base_url", Config.AI_BASE_URL)

    async def set_ai_base_url(self, base_url: str) -> None:
        await self.set_global_setting("ai_base_url", base_url.rstrip("/"))

    async def get_ai_settings(self) -> dict[str, str]:
        return {
            "api_key": await self.get_ai_api_key(),
            "provider": await self.get_ai_provider(),
            "model": await self.get_ai_model(),
            "base_url": await self.get_ai_base_url(),
        }

    async def is_ai_configured(self) -> bool:
        settings = await self.get_ai_settings()
        return bool(settings["api_key"] and settings["model"])

    async def get_use_webhook(self) -> bool:
        stored = await self.get_global_setting("use_webhook", "")
        if stored:
            return stored.lower() == "true"
        return Config.USE_WEBHOOK

    async def set_use_webhook(self, enabled: bool) -> None:
        await self.set_global_setting("use_webhook", "true" if enabled else "false")

    async def get_webhook_url(self) -> str:
        stored = await self.get_global_setting("webhook_url", "")
        return stored or Config.WEBHOOK_URL

    async def set_webhook_url(self, url: str) -> None:
        await self.set_global_setting("webhook_url", url.rstrip("/"))

    async def get_cf_tunnel_token(self) -> str:
        return await self.get_global_setting("cf_tunnel_token", "")

    async def set_cf_tunnel_token(self, token: str) -> None:
        await self.set_global_setting("cf_tunnel_token", token)

    async def get_webhook_settings(self) -> dict[str, str]:
        return {
            "use_webhook": "true" if await self.get_use_webhook() else "false",
            "webhook_url": await self.get_webhook_url(),
            "cf_tunnel_token": await self.get_cf_tunnel_token(),
        }

    async def get_global_stats(self) -> dict[str, Any]:
        groups = await self._fetchall(
            "SELECT chat_id, title, messages_processed FROM groups WHERE is_authorized = 1",
        )
        chat_ids = [g["chat_id"] for g in groups]
        period_stats = await self.get_groups_message_stats_bulk(chat_ids)
        for g in groups:
            stats = period_stats.get(g["chat_id"], {"week": 0, "month": 0})
            g["messages_week"] = stats["week"]
            g["messages_month"] = stats["month"]
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
