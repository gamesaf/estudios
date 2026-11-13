"""Interfaz de Estudio Inteligente con IA."""

import base64
import calendar as pycalendar
import colorsys
import html
import json
import os
import re
import psycopg2
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv

import base_datos
import datos_demo
import motor_ia

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="Estudio Inteligente con IA",
    page_icon="🧠",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        --study-bg: #08090b;
        --study-panel: #111214;
        --study-panel-soft: #191a1d;
        --study-border: #2b2c30;
        --study-text: #ececee;
        --study-muted: #a0a1a6;
        --study-accent: #c1a875;
    }
    .stApp {
        background:
            radial-gradient(ellipse at 12% 0%, rgba(147, 125, 83, .10), transparent 38%),
            var(--study-bg);
        color: var(--study-text);
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1500px;
    }
    .study-hero {
        padding: 1.35rem 1.6rem;
        margin: 0 0 1.4rem;
        border: 1px solid var(--study-border);
        border-radius: 18px;
        background: linear-gradient(115deg, #1b1b1d 0%, #111214 62%, #171614 100%);
        box-shadow: 0 14px 35px rgba(0, 0, 0, .18);
    }
    .study-hero h1 {
        margin: 0;
        color: #f3f7ff;
        font-size: clamp(1.55rem, 3vw, 2.2rem);
        letter-spacing: -.035em;
    }
    .study-hero p {
        margin: .45rem 0 0;
        color: var(--study-muted);
        font-size: 1rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: .45rem;
        border-bottom: 1px solid var(--study-border);
    }
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        padding: 0 1rem;
        border-radius: 10px 10px 0 0;
        color: var(--study-muted);
    }
    .stTabs [aria-selected="true"] {
        color: #fff !important;
        background: rgba(193, 168, 117, .10);
        border-bottom: 2px solid var(--study-accent);
    }
    .stButton > button, .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] > button {
        border-radius: 10px;
        font-weight: 600;
        transition: transform .15s ease, box-shadow .15s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover,
    [data-testid="stFormSubmitButton"] > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 18px rgba(0, 0, 0, .28);
        border-color: var(--study-accent);
    }
    .stButton button[kind="primary"],
    [data-testid="stFormSubmitButton"] button[kind="primary"] {
        background: #786443;
        border-color: #9a8157;
        color: #fff;
    }
    [data-testid="stMetric"] {
        padding: .8rem 1rem;
        border: 1px solid var(--study-border);
        border-radius: 12px;
        background: rgba(24, 25, 27, .88);
    }
    [data-testid="stMetricLabel"] { color: var(--study-muted); }
    [data-testid="stExpander"] {
        border-color: var(--study-border);
        border-radius: 12px;
        background: rgba(17, 28, 48, .55);
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--study-border);
        border-radius: 14px;
        background: linear-gradient(145deg, rgba(25, 26, 28, .9), rgba(15, 16, 18, .9));
    }
    .exam-picker-card {
        padding: .75rem .85rem;
        margin: .25rem 0 .45rem;
        border: 1px solid #303135;
        border-radius: 12px;
        background: linear-gradient(145deg, #191a1c, #111214);
    }
    .exam-picker-card.selected {
        border-color: var(--study-accent);
        box-shadow: inset 3px 0 0 var(--study-accent);
        background: linear-gradient(145deg, #211f1a, #151514);
    }
    .exam-picker-title {
        margin: 0 0 .35rem;
        color: #f0f0f1;
        font-size: 1rem;
        font-weight: 650;
    }
    .exam-picker-meta {
        color: var(--study-muted);
        font-size: .82rem;
        line-height: 1.5;
    }
    .exam-picker-card + div button {
        border-color: #36373a;
    }
    h2, h3 { letter-spacing: -.02em; }
    </style>
    """,
    unsafe_allow_html=True,
)

DAYS_OF_WEEK = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _theme_color(value: str) -> str:
    if (
        isinstance(value, str)
        and len(value) == 7
        and value.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        return value
    return "#786443"


def _color_name(value: str) -> str:
    color = _theme_color(value)
    red, green, blue = (int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if saturation < 0.18:
        return "gris claro" if lightness > 0.72 else "gris oscuro" if lightness < 0.3 else "gris"
    degrees = hue * 360
    if degrees < 15 or degrees >= 345:
        return "rojo"
    if degrees < 42:
        return "naranja"
    if degrees < 68:
        return "amarillo"
    if degrees < 165:
        return "verde"
    if degrees < 195:
        return "turquesa"
    if degrees < 255:
        return "azul"
    if degrees < 290:
        return "morado"
    if degrees < 345:
        return "rosa"
    return "gris"


def _render_note_cards(notes: Any) -> None:
    structured = notes if isinstance(notes, dict) else None
    if isinstance(notes, str):
        try:
            parsed = json.loads(notes)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and "tarjetas" in parsed:
            structured = parsed

    if structured is not None:
        fidelity_note = structured.get("nota_fidelidad", "").strip()
        if fidelity_note:
            st.info(f"**Nota de lectura:** {fidelity_note}")
        for warning in structured.get("fragmentos_ilegibles", []):
            st.warning(f"**Fragmento no legible:** {warning}")

        cards = structured.get("tarjetas", [])
        if not cards:
            st.info("No se pudieron estructurar tarjetas para este bloque.")
        for card_index, card in enumerate(cards):
            title = card.get("titulo") or f"Concepto {card_index + 1}"
            with st.expander(
                f"📘 {title}",
                expanded=card_index == 0,
            ):
                with st.container(border=True):
                    if card.get("idea_principal"):
                        st.markdown(f"**Idea principal**\n\n{card['idea_principal']}")
                    concepts = card.get("conceptos_clave", [])
                    if concepts:
                        st.markdown("**Conceptos clave**")
                        st.markdown(
                            " · ".join(f"`{concept}`" for concept in concepts)
                        )
                    if card.get("explicacion"):
                        st.markdown("**Explicación**")
                        st.markdown(card["explicacion"])
                    if card.get("relaciones"):
                        st.markdown("**Relación o pasos**")
                        st.markdown(card["relaciones"])

                    pages = card.get("paginas_fuente", [])
                    if pages:
                        page_labels = ", ".join(
                            f"imagen {page}" for page in pages
                        )
                        st.caption(f"Fuente: {page_labels}")

                    visual = card.get("elemento_visual")
                    if visual:
                        st.info(
                            f"**{visual.get('tipo', 'Recurso visual').capitalize()}:** "
                            f"{visual.get('descripcion', '')}"
                        )

                    recall_questions = card.get("preguntas_recuerdo", [])
                    if recall_questions:
                        with st.expander("🧠 Preguntas para recordar"):
                            for question_index, question in enumerate(
                                recall_questions
                            ):
                                st.markdown(
                                    f"**{question_index + 1}. "
                                    f"{question.get('pregunta', '')}**"
                                )
                                with st.expander("Mostrar respuesta"):
                                    st.write(question.get("respuesta", ""))
        return

    content = (
        notes if isinstance(notes, str) else "No hay apuntes sintetizados para esta sesión."
    ).strip()
    if content.startswith("{") and structured is None:
        st.warning("No se pudo interpretar el formato estructurado de estos apuntes.")
    sections = re.split(r"(?m)(?=^#{1,3}\s+)", content)
    if len(sections) == 1:
        sections = [
            section.strip()
            for section in re.split(r"\n\s*\n", content)
            if section.strip()
        ]
    if (
        len(sections) == 1
        and not re.match(r"^\s*(?:[-*+]|\d+[.)])\s", sections[0])
    ):
        sentences = re.split(
            r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ0-9])",
            sections[0].strip(),
        )
        if len(sentences) > 1:
            sections = sentences
    for section_index, section in enumerate(sections):
        if section.strip():
            heading = section.strip().splitlines()[0].lstrip("# ").strip()
            with st.expander(
                heading or f"Apunte {section_index + 1}",
                expanded=section_index == 0,
            ):
                with st.container(border=True):
                    st.markdown(section.strip())


@st.dialog("Apuntes de la sesión", width="large", dismissible=False)
def _notes_dialog(session: dict[str, Any]) -> None:
    st.caption(
        f"{session['asignatura']} · Bloque {session['bloque']} · "
        f"{session['titulo']}"
    )
    _render_note_cards(session["apuntes"])
    try:
        for visual in json.loads(session["test_json"]).get(
            "elementos_visuales_sugeridos", []
        ):
            st.info(
                f"**{visual.get('tipo', 'Recurso visual').capitalize()}:** "
                f"{visual.get('descripcion', '')}"
            )
    except json.JSONDecodeError as error:
        st.error(f"No se pudieron leer las sugerencias visuales: {error}")
    if st.button("Cerrar", key=f"cerrar_apuntes_{session['id']}"):
        st.session_state.pop("modal_sesion", None)
        st.rerun()


@st.dialog("Test de la sesión", width="large", dismissible=False)
def _test_dialog(
    session: dict[str, Any],
    questions: list[dict[str, Any]],
) -> None:
    st.caption(
        f"{session['asignatura']} · Bloque {session['bloque']} · "
        f"{session['titulo']}"
    )
    previous_attempt = base_datos.obtener_intento_sesion(session["id"])
    if previous_attempt:
        feedback = json.loads(previous_attempt["feedback_json"])
        st.success(f"Intento realizado · Nota: {previous_attempt['nota']:.1f}/10")
        st.markdown(feedback.get("comentario_general", ""))
        for result in feedback.get("resultados", []):
            st.markdown(f"**Pregunta {result.get('id_pregunta')}**")
            st.write(result.get("comentario", ""))
            st.caption(f"Respuesta esperada: {result.get('respuesta_esperada', '')}")
    elif not questions:
        st.info("Este bloque no tiene preguntas disponibles.")
    else:
        st.markdown(f"Responde las **{len(questions)} preguntas**.")
        with st.form(f"responder_test_{session['id']}"):
            answers: dict[int, str] = {}
            for question in questions:
                question_id = int(question["id"])
                label = f"{question_id}. {question['enunciado']}"
                if question.get("tipo_pregunta") == "test":
                    selected = st.radio(
                        label,
                        ["Selecciona una opción", *question["opciones"]],
                        key=f"respuesta_{session['id']}_{question_id}",
                    )
                    answers[question_id] = (
                        "" if selected == "Selecciona una opción" else selected
                    )
                else:
                    answers[question_id] = st.text_area(
                        label,
                        key=f"respuesta_{session['id']}_{question_id}",
                    )
            submitted = st.form_submit_button("Enviar intento")

        if submitted:
            try:
                with st.spinner("Corrigiendo tus respuestas..."):
                    correction = motor_ia.corregir_test(questions, answers)
                    base_datos.guardar_intento(
                        session["id"],
                        correction["nota"],
                        correction,
                    )
                st.session_state["ultimo_resultado_test"] = {
                    "nota": correction["nota"],
                    "comentario": correction["comentario_general"],
                }
                st.session_state.pop("modal_sesion", None)
                st.rerun()
            except Exception as error:
                st.error(f"No se pudo corregir o guardar el test: {error}")

    if st.button("Cerrar", key=f"cerrar_test_{session['id']}"):
        st.session_state.pop("modal_sesion", None)
        st.rerun()


def _show_session_card(session: dict[str, Any]) -> None:
    session_id = session["id"]
    test_data = json.loads(session["test_json"])
    multiple_choice = test_data.get("preguntas_tipo_test", [])
    development = test_data.get("preguntas_desarrollo", [])
    legacy_questions = test_data.get("preguntas", [])
    questions: list[dict[str, Any]] = []
    for question in multiple_choice:
        questions.append(
            {
                **question,
                "id": len(questions) + 1,
                "tipo_pregunta": "test",
                "respuesta_correcta": question["respuesta_correcta"],
            }
        )
    for question in development:
        questions.append(
            {
                **question,
                "id": len(questions) + 1,
                "tipo_pregunta": "desarrollo",
                "respuesta_correcta": question["criterios_evaluacion"],
            }
        )
    if not multiple_choice and not development:
        questions = legacy_questions

    color = _theme_color(session.get("color_tema", ""))
    with st.container(border=True):
        st.markdown(
            f"<div style='height:5px;border-radius:5px;background:{color};"
            "margin:-.2rem 0 .8rem'></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"📅 Sesión: {session['fecha_sesion']} · "
            f"{session['asignatura']} · Bloque {session['bloque']}"
        )
        st.markdown(f"### {session['titulo']}")
        st.caption(
            f"Color de asignatura: **{_color_name(color).capitalize()}**"
        )
        action_col, test_col, complete_col = st.columns([1, 1, 1.15])
        if action_col.button(
            "Generar Apuntes",
            key=f"notas_{session_id}",
            use_container_width=True,
        ):
            st.session_state["modal_sesion"] = {
                "tipo": "apuntes",
                "id": session_id,
            }
        attempted = session.get("intentos_realizados", 0) > 0
        if test_col.button(
            "Test realizado" if attempted else "Generar un Test",
            key=f"test_{session_id}",
            use_container_width=True,
            disabled=attempted or not questions,
        ):
            st.session_state["modal_sesion"] = {
                "tipo": "test",
                "id": session_id,
            }
        completed = bool(session.get("completada", 0))
        if complete_col.button(
            "Sesión realizada ✓" if completed else "Sesión realizada",
            key=f"completar_sesion_{session_id}",
            use_container_width=True,
            disabled=completed,
        ):
            try:
                base_datos.marcar_sesion_realizada(session_id)
                st.rerun()
            except (psycopg2.Error, ValueError) as error:
                st.error(f"No se pudo marcar la sesión como realizada: {error}")

    modal = st.session_state.get("modal_sesion", {})
    if modal.get("id") == session_id:
        if modal.get("tipo") == "apuntes":
            _notes_dialog(session)
        elif modal.get("tipo") == "test":
            _test_dialog(session, questions)


def _organization_tab() -> None:
    st.markdown("### Organiza tu estudio")
    st.caption("Crea un plan adaptado a tu ritmo y consulta aquí tus próximas sesiones.")
    form_column, sessions_column = st.columns([0.95, 1.25], gap="large")

    with form_column:
        with st.container(border=True):
            st.markdown("#### ✨ Nuevo plan")
            with st.form("form_plan", clear_on_submit=True):
                subject = st.text_input("Asignatura", placeholder="Ej. Física")
                subject_type = st.selectbox("Tipo de asignatura", ["ciencias", "letras"])
                daily_hours = st.slider("Horas disponibles al día", 1.0, 8.0, 2.0, 0.5)
                study_days = st.multiselect(
                    "¿Qué días quieres estudiar?",
                    DAYS_OF_WEEK,
                    default=DAYS_OF_WEEK[:5],
                    help="Las sesiones se programarán únicamente en los días seleccionados.",
                )
                exam_date = st.date_input(
                    "Fecha del examen (opcional)",
                    value=None,
                    min_value=date.today(),
                    format="DD/MM/YYYY",
                    help="Déjalo vacío si todavía no tienes fecha de examen.",
                )
                if exam_date:
                    days_until_exam = (exam_date - date.today()).days
                    if study_days:
                        available_study_dates = base_datos.fechas_estudio_disponibles(
                            exam_date,
                            [DAYS_OF_WEEK.index(day) for day in study_days],
                        )
                        st.caption(
                            f"Hay {len(available_study_dates)} días seleccionados para "
                            f"estudiar antes del examen ({days_until_exam} días "
                            "restantes). La IA ajustará los bloques a ese tiempo."
                        )
                    else:
                        st.caption(
                            f"Las sesiones se repartirán antes del examen "
                            f"({days_until_exam} días restantes)."
                        )
                else:
                    st.caption(
                        "Sin fecha de examen, las sesiones empezarán en el próximo día "
                        "que hayas seleccionado."
                    )
                image_files = st.file_uploader(
                    "Apuntes en imágenes",
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=True,
                    help="Puedes subir varias páginas en formato PNG o JPG.",
                )
                submitted = st.form_submit_button(
                    "Generar plan con IA",
                    type="primary",
                    use_container_width=True,
                )

        if submitted:
            if not subject.strip():
                st.warning("Escribe el nombre de la asignatura.")
            elif not study_days:
                st.warning("Selecciona al menos un día para estudiar.")
            elif not image_files:
                st.warning("Sube al menos una imagen de tus apuntes.")
            else:
                study_day_numbers = [DAYS_OF_WEEK.index(day) for day in study_days]
                available_study_dates = (
                    base_datos.fechas_estudio_disponibles(
                        exam_date, study_day_numbers
                    )
                    if exam_date
                    else None
                )
                if exam_date and not available_study_dates:
                    st.warning(
                        "No hay ningún día seleccionado para estudiar antes del "
                        "examen. Elige otros días o una fecha posterior."
                    )
                else:
                    try:
                        existing_exams = base_datos.obtener_examenes()
                        existing_sessions = base_datos.obtener_sesiones()
                        planning_deadline = exam_date or (
                            date.today() + timedelta(days=60)
                        )
                        pending_by_exam: dict[int, int] = {}
                        for existing_session in existing_sessions:
                            if (
                                not existing_session.get("completada", 0)
                                and date.fromisoformat(
                                    existing_session["fecha_sesion"]
                                )
                                <= planning_deadline
                            ):
                                plan_id = existing_session["plan_id"]
                                pending_by_exam[plan_id] = (
                                    pending_by_exam.get(plan_id, 0) + 1
                                )
                        other_exams = [
                            {
                                "asignatura": existing_exam["asignatura"],
                                "fecha_examen": existing_exam["fecha_examen"],
                                "sesiones_pendientes": pending_by_exam.get(
                                    existing_exam["id"], 0
                                ),
                            }
                            for existing_exam in existing_exams
                            if not existing_exam["es_demo"]
                            and existing_exam["fecha_examen"]
                            and date.today()
                            <= date.fromisoformat(existing_exam["fecha_examen"])
                            <= planning_deadline
                        ]
                        with st.spinner(
                            "La IA está leyendo tus apuntes y creando las sesiones..."
                        ):
                            plan = motor_ia.generar_plan(
                                image_files,
                                subject.strip(),
                                subject_type,
                                daily_hours,
                                study_days,
                                exam_date,
                                available_study_dates,
                                other_exams,
                            )
                            plan_id = base_datos.guardar_plan(
                                subject.strip(),
                                subject_type,
                                daily_hours,
                                exam_date,
                                plan,
                                study_day_numbers,
                            )
                        st.session_state["examen_seleccionado"] = plan_id
                        if exam_date:
                            st.success(
                                f"Plan guardado. Las sesiones se han distribuido hasta "
                                f"antes del examen del {exam_date.strftime('%d/%m/%Y')}."
                            )
                        else:
                            st.success("Plan generado y guardado.")
                    except Exception as error:
                        st.error(f"No se pudo generar el plan: {error}")

        result = st.session_state.pop("ultimo_resultado_test", None)
        if result:
            st.success(f"Test corregido: nota {result['nota']:.1f}/10. {result['comentario']}")

    with sessions_column:
        st.markdown("#### 📚 Tus sesiones")
        try:
            sessions = base_datos.obtener_sesiones()
            active_sessions = [
                session for session in sessions if not session.get("completada", 0)
            ]
            if not active_sessions and not sessions:
                st.info("Cuando generes tu primer plan, tus sesiones aparecerán aquí.")
            elif not active_sessions:
                st.success("¡Has completado todas tus sesiones pendientes!")
            else:
                upcoming_sessions = sum(
                    date.fromisoformat(session["fecha_sesion"]) >= date.today()
                    for session in active_sessions
                )
                session_metrics = st.columns(2)
                session_metrics[0].metric("Bloques pendientes", len(active_sessions))
                session_metrics[1].metric("Próximos", upcoming_sessions)
                for session in active_sessions:
                    _show_session_card(session)
        except psycopg2.Error as error:
            st.error(f"No se pudieron cargar las sesiones: {error}")


def _exam_tab() -> None:
    st.subheader("Mis Exámenes")
    try:
        exams = base_datos.obtener_examenes()
        all_sessions = base_datos.obtener_sesiones()
    except psycopg2.Error as error:
        st.error(f"No se pudieron cargar los exámenes: {error}")
        return

    if not exams:
        st.info("Todavía no hay exámenes guardados. Crea un plan desde Organización.")
        return

    exam_ids = [exam["id"] for exam in exams]
    session_progress: dict[int, list[int]] = {}
    for session in all_sessions:
        counts = session_progress.setdefault(session["plan_id"], [0, 0])
        counts[0] += 1
        counts[1] += int(bool(session.get("completada", 0)))

    saved_selection = st.session_state.get("examen_seleccionado")
    selected_id = saved_selection if saved_selection in exam_ids else exam_ids[0]

    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown("#### 📚 Tus materias")
        st.caption("Elige una tarjeta para consultar el plan y tu progreso.")
        for exam in exams:
            exam_id = exam["id"]
            is_selected = exam_id == selected_id
            exam_plan = json.loads(exam["plan_json"])
            exam_color = _theme_color(exam_plan.get("color_tema", ""))
            exam_date = (
                date.fromisoformat(exam["fecha_examen"])
                if exam["fecha_examen"]
                else None
            )
            if exam_date:
                remaining = (exam_date - date.today()).days
                if remaining > 1:
                    date_status = f"Examen en {remaining} días"
                elif remaining == 1:
                    date_status = "Examen mañana"
                elif remaining == 0:
                    date_status = "Examen hoy"
                else:
                    date_status = f"Examen pasado · {abs(remaining)} días"
                date_line = f"📅 {exam_date.strftime('%d/%m/%Y')} · {date_status}"
            else:
                date_line = "📅 Sin fecha de examen"

            card_class = "exam-picker-card selected" if is_selected else "exam-picker-card"
            demo_badge = (
                " <span style='color:#c1a875;font-size:.72rem'>DEMO</span>"
                if exam["es_demo"]
                else ""
            )
            st.markdown(
                f"<div class='{card_class}' style='border-left:4px solid {exam_color}'>"
                f"<div class='exam-picker-title'>"
                f"{'◈' if is_selected else '◇'} {html.escape(exam['asignatura'])}"
                f"{demo_badge}"
                "</div>"
                f"<div class='exam-picker-meta'>{html.escape(date_line)}<br>"
                f"{html.escape(exam['tipo_asignatura'].capitalize())} · "
                f"{exam['tests_realizados']} tests realizados</div></div>",
                unsafe_allow_html=True,
            )
            total_sessions, done_sessions = session_progress.get(exam_id, [0, 0])
            progress = done_sessions / total_sessions if total_sessions else 0.0
            st.progress(
                progress,
                text=f"Sesiones realizadas: {done_sessions}/{total_sessions}",
            )
            if st.button(
                "✓ Seleccionado" if is_selected else "Ver progreso",
                key=f"seleccionar_examen_{exam_id}",
                type="primary" if is_selected else "secondary",
                use_container_width=True,
                disabled=is_selected,
            ):
                st.session_state["examen_seleccionado"] = exam_id
                st.rerun()

        st.session_state["examen_seleccionado"] = selected_id

    exam = next(item for item in exams if item["id"] == selected_id)
    plan = json.loads(exam["plan_json"])
    attempts = base_datos.obtener_intentos(selected_id)
    with right:
        st.markdown(f"### 📘 {exam['asignatura']}")
        total_sessions, done_sessions = session_progress.get(selected_id, [0, 0])
        progress = done_sessions / total_sessions if total_sessions else 0.0
        st.progress(
            progress,
            text=f"Progreso del plan: {done_sessions}/{total_sessions} sesiones realizadas",
        )
        st.caption(
            f"Tipo: {exam['tipo_asignatura']} · "
            f"Fecha de examen: {exam['fecha_examen'] or 'No definida'}"
        )
        if exam["fecha_examen"]:
            exam_date = date.fromisoformat(exam["fecha_examen"])
            days_remaining = (exam_date - date.today()).days
            if days_remaining > 1:
                st.info(f"📆 Quedan **{days_remaining} días** para este examen.")
            elif days_remaining == 1:
                st.warning("📆 El examen es **mañana**.")
            elif days_remaining == 0:
                st.warning("📆 El examen es **hoy**.")
            else:
                st.caption(f"El examen fue hace {abs(days_remaining)} días.")
        metric_columns = st.columns(3)
        metric_columns[0].metric("Tests realizados", exam["tests_realizados"])
        metric_columns[1].metric(
            "Nota más alta",
            f"{exam['nota_maxima']:.1f}/10" if exam["nota_maxima"] is not None else "—",
        )
        metric_columns[2].metric(
            "Nota media",
            f"{exam['nota_media']:.1f}/10" if exam["nota_media"] is not None else "—",
        )

        theme_color = _theme_color(plan.get("color_tema", ""))
        st.markdown(
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"border-radius:50%;background:{theme_color};margin-right:7px'></span>"
            f"Color de la asignatura: **{_color_name(theme_color).capitalize()}**",
            unsafe_allow_html=True,
        )

        st.markdown("#### Apuntes sintetizados")
        planned_sessions = plan.get(
            "planificacion_sesiones", plan.get("planificacion", [])
        )
        for session in planned_sessions:
            block = session.get("bloque", session.get("sesion_id", 1))
            title = session.get("titulo_sesion") or f"Bloque {block}"
            notes = session.get(
                "apuntes_sintetizados_modal",
                session.get("apuntes_sintetizados", ""),
            )
            with st.expander(f"Bloque {block}: {title}"):
                _render_note_cards(notes)
                for visual in session.get("elementos_visuales_sugeridos", []):
                    st.markdown(
                        f"**{visual.get('tipo', 'Recurso visual').capitalize()}:** "
                        f"{visual.get('descripcion', '')}"
                    )

        st.markdown("#### Historial de tests corregidos")
        if not attempts:
            st.caption("Aún no has realizado tests de este examen.")
        for attempt in attempts:
            feedback = json.loads(attempt["feedback_json"])
            with st.expander(
                f"Bloque {attempt['bloque']} · {attempt['creado_en']} · "
                f"Nota {attempt['nota']:.1f}/10"
            ):
                st.write(feedback.get("comentario_general", ""))
                for item in feedback.get("resultados", []):
                    status = "✅" if item.get("correcta") else "❌"
                    st.markdown(f"{status} **Pregunta {item.get('id_pregunta')}**")
                    st.write(item.get("comentario", ""))
                    st.caption(f"Respuesta esperada: {item.get('respuesta_esperada', '')}")

        st.download_button(
            "Descargar plan (JSON)",
            data=json.dumps(plan, ensure_ascii=False, indent=2),
            file_name=f"plan_{exam['asignatura'].lower().replace(' ', '_')}.json",
            mime="application/json",
            key=f"descargar_examen_{selected_id}",
        )
        if st.session_state.get("examen_a_eliminar") == selected_id:
            st.warning("¿Eliminar este examen, sus sesiones y sus tests? No se puede deshacer.")
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button("Sí, eliminar", key=f"confirmar_examen_{selected_id}"):
                base_datos.eliminar_examen(selected_id)
                st.session_state.pop("examen_a_eliminar", None)
                st.session_state.pop("examen_seleccionado", None)
                st.rerun()
            if cancel_column.button("Cancelar", key=f"cancelar_examen_{selected_id}"):
                st.session_state.pop("examen_a_eliminar", None)
                st.rerun()
        elif st.button("🗑️ Eliminar este examen", key=f"eliminar_examen_{selected_id}"):
            st.session_state["examen_a_eliminar"] = selected_id
            st.rerun()


def _calendar_tab() -> None:
    try:
        sessions = base_datos.obtener_sesiones()
        exams = base_datos.obtener_examenes()
    except psycopg2.Error as error:
        st.error(f"No se pudo cargar el calendario: {error}")
        return

    events: dict[date, list[dict[str, str]]] = {}
    for session in sessions:
        if session.get("completada", 0):
            continue
        event_date = date.fromisoformat(session["fecha_sesion"])
        events.setdefault(event_date, []).append(
            {
                "tipo": "Sesión",
                "asignatura": session["asignatura"],
                "titulo": f"Bloque {session['bloque']}: {session['titulo']}",
            }
        )
    for exam in exams:
        if exam["fecha_examen"]:
            event_date = date.fromisoformat(exam["fecha_examen"])
            events.setdefault(event_date, []).append(
                {
                    "tipo": "Examen",
                    "asignatura": exam["asignatura"],
                    "titulo": "Fecha de examen",
                }
            )

    if "calendario_mes" not in st.session_state:
        st.session_state["calendario_mes"] = date.today().replace(day=1)

    month = st.session_state["calendario_mes"]
    previous, heading, following = st.columns([1, 6, 1])

    if previous.button("‹", key="calendario_anterior", use_container_width=True):
        st.session_state["calendario_mes"] = (
            month - timedelta(days=1)
        ).replace(day=1)
        st.rerun()

    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    heading.markdown(
        f"<h3 style='text-align:center;margin:0.35rem 0'>"
        f"📅 Calendario de Estudio y Exámenes · "
        f"{months[month.month - 1]} {month.year}</h3>",
        unsafe_allow_html=True,
    )

    if following.button("›", key="calendario_siguiente", use_container_width=True):
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.session_state["calendario_mes"] = next_month
        st.rerun()

    month_events = [
        event
        for event_date, day_events in events.items()
        if event_date.year == month.year and event_date.month == month.month
        for event in day_events
    ]
    summary = st.columns(3)
    summary[0].metric("Eventos este mes", len(month_events))
    summary[1].metric(
        "Sesiones",
        sum(event["tipo"] == "Sesión" for event in month_events),
    )
    summary[2].metric(
        "Exámenes",
        sum(event["tipo"] == "Examen" for event in month_events),
    )

    st.markdown(
        """
        <style>
        .calendar-shell {
            background: linear-gradient(145deg, #151618, #0d0e10);
            border: 1px solid #303135;
            border-radius: 18px;
            padding: 16px;
            box-shadow: 0 16px 38px rgba(0, 0, 0, .22);
        }
        .calendar-weekdays, .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 7px;
        }
        .calendar-weekday {
            background: #202124;
            color: #c2c2c5;
            text-align: center;
            padding: 10px 2px;
            border: 1px solid #303135;
            border-radius: 9px;
            font-weight: 600;
            letter-spacing: .02em;
        }
        .calendar-day {
            box-sizing: border-box;
            min-height: 100px;
            padding: 8px;
            background: rgba(13, 14, 16, .92);
            border: 1px solid #26272a;
            border-radius: 12px;
            overflow: hidden;
            transition: border-color .15s ease, background .15s ease, transform .15s ease;
        }
        .calendar-day:not(.empty):hover {
            background: #1a1b1d;
            border-color: #55565a;
            transform: translateY(-1px);
        }
        .calendar-day.empty {
            background: rgba(13, 14, 16, .3);
            border-color: rgba(38, 39, 42, .45);
        }
        .calendar-number {
            color: #dedee0;
            font-weight: 600;
            font-size: 13px;
            margin-bottom: 8px;
        }
        .calendar-day.today {
            border: 1px solid #b39a69;
            box-shadow: 0 0 0 1px rgba(179, 154, 105, .24) inset;
        }
        .calendar-day.today .calendar-number {
            display: inline-block;
            background: #786443;
            border-radius: 50%;
            padding: 3px 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, .35);
        }
        .calendar-event {
            display: block;
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
            padding: 5px 6px;
            margin: 3px 0;
            border-radius: 7px;
            font-size: 12px;
            font-weight: 550;
        }
        .calendar-event.session {
            color: #ded3bc;
            background: linear-gradient(90deg, #302a20, #24211c);
            border: 1px solid #514531;
        }
        .calendar-event.exam {
            color: #e7c2c2;
            background: linear-gradient(90deg, #392526, #282021);
            border: 1px solid #634143;
        }
        @media (max-width: 700px) {
            .calendar-shell { padding: 7px; }
            .calendar-weekdays, .calendar-grid { gap: 3px; }
            .calendar-day { min-height: 68px; padding: 4px; border-radius: 8px; }
            .calendar-event { font-size: 10px; padding: 3px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    weekday_html = "".join(
        f"<div class='calendar-weekday'>{day}</div>" for day in weekdays
    )
    first_weekday, days_in_month = pycalendar.monthrange(month.year, month.month)
    cells = ["<div class='calendar-day empty'></div>" for _ in range(first_weekday)]

    for day_number in range(1, days_in_month + 1):
        current_date = date(month.year, month.month, day_number)
        today_class = " today" if current_date == date.today() else ""
        event_html = ""

        for event in events.get(current_date, []):
            event_class = "exam" if event["tipo"] == "Examen" else "session"
            label = f"{event['asignatura']}: {event['titulo']}"
            escaped_label = html.escape(label)
            escaped_title = html.escape(label, quote=True)
            event_html += (
                f"<div class='calendar-event {event_class}' "
                f"title='{escaped_title}'>{escaped_label}</div>"
            )

        cells.append(
            f"<div class='calendar-day{today_class}'>"
            f"<div class='calendar-number'>{day_number}</div>"
            f"{event_html}</div>"
        )

    while len(cells) % 7:
        cells.append("<div class='calendar-day empty'></div>")

    st.markdown(
        "<div class='calendar-shell'>"
        f"<div class='calendar-weekdays'>{weekday_html}</div><br>"
        f"<div class='calendar-grid'>{''.join(cells)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    legend_sessions, legend_exams = st.columns(2)
    legend_sessions.markdown("🔹 **Sesiones de estudio**")
    legend_exams.markdown("🔸 **Fechas de examen**")


try:
    base_datos.inicializar_base_datos()
except (psycopg2.Error, ValueError, json.JSONDecodeError) as error:
    st.error(f"No se pudo preparar la base de datos: {error}")
    st.stop()

st.markdown(
    """
    <div class="study-hero">
      <h1>🧠 Estudio Inteligente</h1>
      <p>Tu espacio para organizar sesiones, preparar exámenes y avanzar con confianza.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("🧪 Modo de prueba (temporal)", expanded=False):
    demo_count = base_datos.contar_planes_demo()
    st.caption(
        "Carga materias, sesiones y tests ficticios sin subir apuntes ni llamar a Gemini. "
        "Los datos demo se identifican y se pueden borrar sin tocar tus planes reales."
    )
    demo_load, demo_remove = st.columns(2)
    if demo_load.button(
        "Cargar datos de prueba",
        type="primary",
        use_container_width=True,
        disabled=demo_count > 0,
    ):
        try:
            with st.spinner("Preparando datos de demostración..."):
                created = datos_demo.cargar_datos_demo()
            if created:
                st.session_state.pop("examen_seleccionado", None)
                st.session_state["aviso_datos_demo"] = (
                    f"Se añadieron {created} exámenes de prueba."
                )
                st.rerun()
            st.info("Ya hay datos de demostración cargados.")
        except Exception as error:
            st.error(f"No se pudieron cargar los datos de prueba: {error}")

    if demo_count:
        if demo_remove.button(
            "Eliminar datos de prueba",
            use_container_width=True,
            key="eliminar_datos_demo",
        ):
            st.session_state["confirmar_eliminar_demo"] = True
        if st.session_state.get("confirmar_eliminar_demo"):
            st.warning("Se eliminarán solo los exámenes marcados como DEMO y sus sesiones/tests.")
            confirm_demo, cancel_demo = st.columns(2)
            if confirm_demo.button("Confirmar eliminación", key="confirmar_borrado_demo"):
                try:
                    deleted = base_datos.eliminar_planes_demo()
                    st.session_state.pop("confirmar_eliminar_demo", None)
                    st.session_state.pop("examen_seleccionado", None)
                    st.session_state["aviso_datos_demo"] = (
                        f"Se eliminaron {deleted} exámenes de prueba."
                    )
                    st.rerun()
                except psycopg2.Error as error:
                    st.error(f"No se pudieron eliminar los datos de prueba: {error}")
            if cancel_demo.button("Cancelar", key="cancelar_borrado_demo"):
                st.session_state.pop("confirmar_eliminar_demo", None)
                st.rerun()

if demo_notice := st.session_state.pop("aviso_datos_demo", None):
    st.success(demo_notice)


def _image_analysis_tab() -> None:
    st.markdown("### Analizar una imagen con Gemini")
    st.caption(
        "Envía una imagen y una instrucción a la Edge Function de Supabase."
    )
    uploaded_image = st.file_uploader(
        "Selecciona o arrastra una imagen",
        type=["jpg", "jpeg", "png", "webp"],
        key="supabase_image_upload",
    )
    prompt = st.text_input(
        "Instrucción para la IA",
        placeholder="¿Qué quieres que analice de la imagen?",
        key="supabase_image_prompt",
    )

    if not st.button("Analizar imagen", type="primary", key="analyze_supabase_image"):
        return
    if uploaded_image is None:
        st.error("Sube una imagen antes de continuar.")
        return
    if not prompt.strip():
        st.error("Escribe una instrucción para la IA.")
        return

    try:
        supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get(
            "SUPABASE_URL", ""
        )
        anon_key = os.getenv("SUPABASE_ANON_KEY") or st.secrets.get(
            "SUPABASE_ANON_KEY", ""
        )
    except FileNotFoundError:
        supabase_url = os.getenv("SUPABASE_URL", "")
        anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key:
        st.error(
            "Configura SUPABASE_URL y SUPABASE_ANON_KEY en el entorno "
            "o en Streamlit Secrets."
        )
        return

    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    image_format = Path(uploaded_image.name).suffix.lower().lstrip(".")
    mime_type = mime_types.get(image_format)
    if mime_type is None:
        st.error("Formato de imagen no compatible. Usa JPG, PNG o WebP.")
        return

    image_base64 = (
        f"data:{mime_type};base64,"
        f"{base64.b64encode(uploaded_image.getvalue()).decode('ascii')}"
    )
    endpoint = f"{supabase_url.rstrip('/')}/functions/v1/analizar-foto"
    headers = {
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
    }

    try:
        with st.spinner("Analizando la imagen..."):
            response = requests.post(
                endpoint,
                headers=headers,
                json={"imageBase64": image_base64, "prompt": prompt.strip()},
                timeout=(10, 180),
            )
        response.raise_for_status()
    except requests.Timeout:
        st.error(
            "La Edge Function tardó más de 180 segundos en responder. "
            "Comprueba su estado y los límites de ejecución de Supabase."
        )
        return
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else "?"
        st.error(f"Supabase devolvió un error HTTP ({status_code}).")
        return
    except requests.RequestException as error:
        st.error(f"No se pudo conectar con Supabase: {error}")
        return

    try:
        result = response.json()
    except ValueError:
        result = response.text
    st.write(result)


organization_tab, exams_tab, calendar_tab, image_analysis_tab = st.tabs(
    ["🏠 Organización", "📚 Mis Exámenes", "📅 Calendario", "🖼️ Analizar imagen"]
)
with organization_tab:
    _organization_tab()
with exams_tab:
    _exam_tab()
with calendar_tab:
    _calendar_tab()
with image_analysis_tab:
    _image_analysis_tab()
