"""Persistencia SQLite para planes, sesiones de estudio y tests corregidos."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

DATABASE_PATH = Path(__file__).resolve().parent / "planes_estudio.db"
DAYS_OF_WEEK = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def inicializar_base_datos() -> None:
    """Crea las tablas necesarias y migra los planes guardados anteriormente."""
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS planes_estudio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asignatura TEXT NOT NULL,
                tipo_asignatura TEXT NOT NULL,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                plan_json TEXT NOT NULL
            )
            """
        )

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(planes_estudio)")
        }
        if "fecha_examen" not in columns:
            connection.execute("ALTER TABLE planes_estudio ADD COLUMN fecha_examen TEXT")
        if "horas_diarias" not in columns:
            connection.execute(
                "ALTER TABLE planes_estudio ADD COLUMN horas_diarias REAL NOT NULL DEFAULT 2"
            )
        if "es_demo" not in columns:
            connection.execute(
                "ALTER TABLE planes_estudio ADD COLUMN es_demo INTEGER NOT NULL DEFAULT 0"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sesiones_estudio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL REFERENCES planes_estudio(id) ON DELETE CASCADE,
                posicion INTEGER NOT NULL,
                bloque INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                apuntes TEXT NOT NULL,
                test_json TEXT NOT NULL,
                fecha_sesion TEXT NOT NULL,
                completada INTEGER NOT NULL DEFAULT 0,
                color_tema TEXT NOT NULL DEFAULT '',
                UNIQUE(plan_id, posicion)
            )
            """
        )
        session_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(sesiones_estudio)")
        }
        if "completada" not in session_columns:
            connection.execute(
                "ALTER TABLE sesiones_estudio ADD COLUMN completada INTEGER NOT NULL DEFAULT 0"
            )
        if "color_tema" not in session_columns:
            connection.execute(
                "ALTER TABLE sesiones_estudio ADD COLUMN color_tema TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS intentos_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sesion_id INTEGER NOT NULL REFERENCES sesiones_estudio(id) ON DELETE CASCADE,
                nota REAL NOT NULL,
                feedback_json TEXT NOT NULL,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sesiones_fecha ON sesiones_estudio(fecha_sesion)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_intentos_sesion ON intentos_test(sesion_id)"
        )
        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_un_intento_por_sesion
            BEFORE INSERT ON intentos_test
            WHEN EXISTS (
                SELECT 1 FROM intentos_test WHERE sesion_id = NEW.sesion_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'Esta sesión ya tiene un intento de test registrado.');
            END
            """
        )

        legacy_plans = connection.execute(
            "SELECT id, creado_en, plan_json FROM planes_estudio"
        ).fetchall()
        for plan in legacy_plans:
            plan_data = json.loads(plan["plan_json"])
            color_tema = plan_data.get("color_tema", "")
            if color_tema:
                connection.execute(
                    """
                    UPDATE sesiones_estudio SET color_tema = ?
                    WHERE plan_id = ? AND color_tema = ''
                    """,
                    (color_tema, plan["id"]),
                )
            exists = connection.execute(
                "SELECT 1 FROM sesiones_estudio WHERE plan_id = ? LIMIT 1",
                (plan["id"],),
            ).fetchone()
            if exists:
                continue

            created = datetime.fromisoformat(plan["creado_en"]).date()
            sessions = plan_data.get(
                "planificacion_sesiones", plan_data.get("planificacion", [])
            )
            for position, session in enumerate(sessions):
                scheduled = created + timedelta(days=position)
                _insert_session(
                    connection,
                    plan_id=plan["id"],
                    position=position,
                    session=session,
                    scheduled_date=scheduled.isoformat(),
                    color_tema=color_tema,
                )


def _insert_session(
    connection: sqlite3.Connection,
    plan_id: int,
    position: int,
    session: dict[str, Any],
    scheduled_date: str,
    color_tema: str = "",
) -> None:
    test = dict(
        session.get("test_evaluacion") or {"tipo": "Repaso", "preguntas": []}
    )
    test["elementos_visuales_sugeridos"] = session.get(
        "elementos_visuales_sugeridos", []
    )
    notes = (
        session.get("apuntes_sintetizados_modal")
        or session.get("apuntes_sintetizados")
        or ""
    )
    if isinstance(notes, dict):
        notes = json.dumps(notes, ensure_ascii=False)
    elif not isinstance(notes, str):
        raise ValueError("Los apuntes sintetizados deben ser texto o un objeto JSON.")
    connection.execute(
        """
        INSERT OR IGNORE INTO sesiones_estudio
            (plan_id, posicion, bloque, titulo, apuntes, test_json, fecha_sesion, color_tema)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_id,
            position,
            int(session.get("bloque", position + 1)),
            session.get("titulo_sesion") or f"Bloque {position + 1}",
            notes,
            json.dumps(test, ensure_ascii=False),
            scheduled_date,
            session.get("color_tema") or color_tema,
        ),
    )


def fechas_estudio_disponibles(
    fecha_examen: date,
    dias_estudio: list[int],
    fecha_inicio: date | None = None,
) -> list[date]:
    """Devuelve los días seleccionados desde el inicio hasta antes del examen."""
    selected_days = set(dias_estudio)
    if not selected_days or any(day < 0 or day > 6 for day in selected_days):
        raise ValueError("Selecciona al menos un día válido para estudiar.")

    current_date = fecha_inicio or date.today()
    available_dates = []
    while current_date < fecha_examen:
        if current_date.weekday() in selected_days:
            available_dates.append(current_date)
        current_date += timedelta(days=1)
    return available_dates


def guardar_plan(
    asignatura: str,
    tipo_asignatura: str,
    horas_diarias: float,
    fecha_examen: date | None,
    datos_plan: dict[str, Any],
    dias_estudio: list[int] | None = None,
    es_demo: bool = False,
) -> int:
    """Guarda un plan y sus sesiones en una sola transacción."""
    canonical_sessions = "planificacion_sesiones" in datos_plan
    sessions = datos_plan.get("planificacion_sesiones") or datos_plan.get(
        "planificacion", []
    )
    today = date.today()
    selected_days = set(range(7) if dias_estudio is None else dias_estudio)
    if not selected_days or any(day < 0 or day > 6 for day in selected_days):
        raise ValueError("Selecciona al menos un día válido para estudiar.")

    scheduled_dates: list[date] = []
    if sessions:
        if fecha_examen:
            candidate_dates = fechas_estudio_disponibles(
                fecha_examen, list(selected_days), today
            )
            if not candidate_dates:
                raise ValueError(
                    "No hay días seleccionados para estudiar antes del examen."
                )

            with _connection() as connection:
                session_load_rows = connection.execute(
                    """
                    SELECT s.fecha_sesion, COUNT(*) AS total
                    FROM sesiones_estudio AS s
                    JOIN planes_estudio AS p ON p.id = s.plan_id
                    WHERE s.completada = 0 AND p.es_demo = 0
                    GROUP BY s.fecha_sesion
                    """
                ).fetchall()
                exam_date_rows = connection.execute(
                    """
                    SELECT fecha_examen
                    FROM planes_estudio
                    WHERE es_demo = 0 AND fecha_examen IS NOT NULL
                    """
                ).fetchall()

            session_load = {
                date.fromisoformat(row["fecha_sesion"]): int(row["total"])
                for row in session_load_rows
            }
            for row in exam_date_rows:
                other_exam_date = date.fromisoformat(row["fecha_examen"])
                session_load[other_exam_date] = (
                    session_load.get(other_exam_date, 0) + len(sessions) + 1
                )

            for index in range(len(sessions)):
                target_index = (
                    round(index * (len(candidate_dates) - 1) / (len(sessions) - 1))
                    if len(sessions) > 1
                    else 0
                )
                chosen_index = min(
                    range(len(candidate_dates)),
                    key=lambda candidate_index: (
                        abs(candidate_index - target_index)
                        + session_load.get(candidate_dates[candidate_index], 0),
                        candidate_index,
                    ),
                )
                chosen_date = candidate_dates[chosen_index]
                scheduled_dates.append(chosen_date)
                session_load[chosen_date] = session_load.get(chosen_date, 0) + 1
        else:
            current_date = today
            while len(scheduled_dates) < len(sessions):
                if current_date.weekday() in selected_days:
                    scheduled_dates.append(current_date)
                current_date += timedelta(days=1)

    if canonical_sessions:
        for session, scheduled_date in zip(sessions, scheduled_dates):
            session["dia_asignado"] = DAYS_OF_WEEK[scheduled_date.weekday()]

    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO planes_estudio
                (asignatura, tipo_asignatura, horas_diarias, fecha_examen, plan_json, es_demo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                asignatura.strip(),
                tipo_asignatura,
                horas_diarias,
                fecha_examen.isoformat() if fecha_examen else None,
                json.dumps(datos_plan, ensure_ascii=False),
                int(es_demo),
            ),
        )
        plan_id = int(cursor.lastrowid)
        for position, session in enumerate(sessions):
            _insert_session(
                connection,
                plan_id,
                position,
                session,
                scheduled_dates[position].isoformat(),
                datos_plan.get("color_tema", ""),
            )
    return plan_id


def obtener_examenes() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.asignatura, p.tipo_asignatura, p.creado_en,
                   p.fecha_examen, p.horas_diarias, p.plan_json, p.es_demo,
                   COUNT(DISTINCT i.id) AS tests_realizados,
                   COUNT(DISTINCT s.id) AS sesiones_totales,
                   COUNT(DISTINCT CASE WHEN s.completada = 1 THEN s.id END)
                       AS sesiones_realizadas,
                   MAX(i.nota) AS nota_maxima,
                   AVG(i.nota) AS nota_media
            FROM planes_estudio AS p
            LEFT JOIN sesiones_estudio AS s ON s.plan_id = p.id
            LEFT JOIN intentos_test AS i ON i.sesion_id = s.id
            GROUP BY p.id
            ORDER BY p.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def marcar_sesion_realizada(sesion_id: int) -> None:
    """Marca una sesión como realizada; la operación es idempotente."""
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE sesiones_estudio SET completada = 1 WHERE id = ?",
            (sesion_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No se encontró la sesión con ID {sesion_id}.")


def obtener_intento_sesion(sesion_id: int) -> dict[str, Any] | None:
    """Devuelve el intento más reciente de una sesión, si existe."""
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM intentos_test
            WHERE sesion_id = ?
            ORDER BY creado_en DESC, id DESC
            LIMIT 1
            """,
            (sesion_id,),
        ).fetchone()
    return dict(row) if row else None


def obtener_sesiones(plan_id: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT s.*, p.asignatura, p.tipo_asignatura, p.fecha_examen,
               (SELECT COUNT(*) FROM intentos_test AS i WHERE i.sesion_id = s.id)
                   AS intentos_realizados
        FROM sesiones_estudio AS s
        JOIN planes_estudio AS p ON p.id = s.plan_id
    """
    parameters: tuple[Any, ...] = ()
    if plan_id is not None:
        query += " WHERE s.plan_id = ?"
        parameters = (plan_id,)
    query += " ORDER BY s.fecha_sesion, s.posicion"
    with _connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def obtener_intentos(plan_id: int) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT i.*, s.bloque, s.titulo, s.test_json
            FROM intentos_test AS i
            JOIN sesiones_estudio AS s ON s.id = i.sesion_id
            WHERE s.plan_id = ?
            ORDER BY i.creado_en DESC, i.id DESC
            """,
            (plan_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def guardar_intento(sesion_id: int, nota: float, feedback: dict[str, Any]) -> None:
    with _connection() as connection:
        existing_attempt = connection.execute(
            "SELECT 1 FROM intentos_test WHERE sesion_id = ? LIMIT 1",
            (sesion_id,),
        ).fetchone()
        if existing_attempt:
            raise ValueError("Esta sesión ya tiene un intento de test registrado.")
        connection.execute(
            "INSERT INTO intentos_test (sesion_id, nota, feedback_json) VALUES (?, ?, ?)",
            (sesion_id, nota, json.dumps(feedback, ensure_ascii=False)),
        )


def eliminar_examen(plan_id: int) -> None:
    with _connection() as connection:
        cursor = connection.execute("DELETE FROM planes_estudio WHERE id = ?", (plan_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"No se encontró el plan con ID {plan_id}.")


def contar_planes_demo() -> int:
    with _connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM planes_estudio WHERE es_demo = 1"
        ).fetchone()
    return int(row["total"])


def eliminar_planes_demo() -> int:
    with _connection() as connection:
        cursor = connection.execute("DELETE FROM planes_estudio WHERE es_demo = 1")
    return cursor.rowcount
