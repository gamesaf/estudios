import os
import json
import sqlite3
from io import BytesIO
from pathlib import Path
from contextlib import closing
from typing import List

import streamlit as st
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
except Exception as exc:  # pragma: no cover - depende del entorno del usuario
    genai = None
    types = None
    GOOGLE_GENAI_IMPORT_ERROR = exc
else:
    GOOGLE_GENAI_IMPORT_ERROR = None

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "planes_estudio.db"
load_dotenv(BASE_DIR / ".env")
api_key = os.getenv("GEMINI_API_KEY")

# Configuración básica de la página web
st.set_page_config(page_title="Plataforma de Estudio IA", layout="centered")

st.title("🧠 Estudio Inteligente con IA")
st.write("Sube tus apuntes y deja que la IA organice tu calendario Pomodoro y tus tests.")

# ==========================================
# ESQUEMA DE DATOS CON PYDANTIC (Type Safety)
# ==========================================
class PreguntaTest(BaseModel):
    id: int = Field(description="Identificador único numérico de la pregunta")
    enunciado: str = Field(description="Enunciado claro de la pregunta de evaluación")
    respuesta_correcta: str = Field(description="Respuesta correcta detallada")

class TestEvaluacion(BaseModel):
    tipo: str = Field(description="Tipo de test, por ejemplo: practico o teorico")
    preguntas: List[PreguntaTest] = Field(description="Lista de preguntas de evaluación")

class SesionPlan(BaseModel):
    bloque: int = Field(description="Número de bloque de estudio")
    titulo_sesion: str = Field(description="Título descriptivo de la sesión")
    apuntes_sintetizados: str = Field(description="Resumen de los apuntes en formato Markdown")
    test_evaluacion: TestEvaluacion

class PlanEstudioResponse(BaseModel):
    asignatura: str
    tipo_asignatura: str
    planificacion: List[SesionPlan]


def mostrar_plan(datos_json):
    asignatura = datos_json.get("asignatura", "Plan de estudio")
    tipo_asignatura = datos_json.get("tipo_asignatura", "")
    sesiones = datos_json.get("planificacion", [])

    st.subheader(f"📘 {asignatura}")
    if tipo_asignatura:
        st.caption(f"Tipo de asignatura: {tipo_asignatura}")

    if not sesiones:
        st.info("Este plan todavía no tiene bloques de estudio.")
        return

    total_preguntas = sum(
        len((sesion.get("test_evaluacion") or {}).get("preguntas", []))
        for sesion in sesiones
    )
    metricas = st.columns(2)
    metricas[0].metric("Bloques de estudio", len(sesiones))
    metricas[1].metric("Preguntas de repaso", total_preguntas)

    for sesion in sesiones:
        bloque = sesion.get("bloque", "")
        titulo = sesion.get("titulo_sesion") or "Sesión de estudio"
        test = sesion.get("test_evaluacion") or {}
        preguntas = test.get("preguntas", [])

        with st.container(border=True):
            st.markdown(f"### 📚 Bloque {bloque}: {titulo}")
            st.markdown("**Resumen de los apuntes**")
            st.markdown(sesion.get("apuntes_sintetizados") or "No hay resumen para este bloque.")

            if preguntas:
                tipo_test = test.get("tipo", "Repaso")
                st.markdown(f"**🧠 {tipo_test} · {len(preguntas)} preguntas**")
                for pregunta in preguntas:
                    pregunta_id = pregunta.get("id", "")
                    enunciado = pregunta.get("enunciado") or "Pregunta"
                    with st.expander(f"Pregunta {pregunta_id}: {enunciado}"):
                        st.markdown("**Respuesta correcta**")
                        st.markdown(pregunta.get("respuesta_correcta") or "No hay respuesta disponible.")
            else:
                st.caption("Este bloque no tiene preguntas de evaluación.")


def convertir_imagenes_a_partes(archivos_imagenes):
    partes = []
    for archivo in archivos_imagenes:
        imagen = Image.open(archivo)
        try:
            imagen_rgb = imagen.convert("RGB")
            buffer = BytesIO()
            mime_type = archivo.type or "image/jpeg"
            if mime_type == "image/png":
                imagen_rgb.save(buffer, format="PNG")
                data = buffer.getvalue()
                partes.append(types.Part.from_bytes(data=data, mime_type="image/png"))
            else:
                imagen_rgb.save(buffer, format="JPEG")
                data = buffer.getvalue()
                partes.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
        finally:
            imagen.close()
    return partes


def inicializar_base_datos():
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        with connection:
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


def guardar_plan(asignatura, tipo_asignatura, datos_json):
    plan_json = json.dumps(datos_json, ensure_ascii=False)
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO planes_estudio (asignatura, tipo_asignatura, plan_json)
                VALUES (?, ?, ?)
                """,
                (asignatura, tipo_asignatura, plan_json),
            )


def obtener_planes_guardados(limite=20):
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, asignatura, tipo_asignatura, creado_en, plan_json
            FROM planes_estudio
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    return [dict(row) for row in rows]


def eliminar_plan(plan_id):
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM planes_estudio WHERE id = ?",
                (plan_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"No se encontró el plan con ID {plan_id}.")


try:
    inicializar_base_datos()
    base_datos_disponible = True
except sqlite3.Error as error:
    base_datos_disponible = False
    st.error(f"No se pudo inicializar la base de datos local: {error}")


if GOOGLE_GENAI_IMPORT_ERROR:
    st.error(
        "La librería de Gemini no puede cargarse en este entorno. "
        "Esto suele pasar con Python 3.13 alpha / versiones incompatibles de pydantic. "
        f"Error exacto: {GOOGLE_GENAI_IMPORT_ERROR}"
    )
    st.warning("Solución: usa Python 3.12 o 3.11 y reinstala dependencias con: pip install -r requirements.txt")
elif not api_key:
    st.error("No se ha encontrado la API Key en el archivo .env. Por favor, revísalo.")
else:
    client = genai.Client(api_key=api_key)

    with st.form("form_apuntes"):
        asignatura = st.text_input("Nombre de la Asignatura", "Física Cuántica")
        tipo_asignatura = st.selectbox("Tipo de Asignatura", ["ciencias", "letras"])
        horas_diarias = st.slider("Horas disponibles al día", 1.0, 8.0, 2.0)

        archivos_imagenes = st.file_uploader(
            "Sube tus apuntes (pueden ser varias fotos en PNG o JPG)",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button("Generar Plan de Estudio con IA")

    if submitted:
        if not archivos_imagenes:
            st.warning("Por favor, sube al menos una imagen de tus apuntes para que la IA pueda procesarla.")
        else:
            with st.spinner("La IA está analizando tus apuntes y estructurando tu plan..."):
                try:
                    prompt_sistema = (
                        "Eres un Arquitecto Educativo experto. Analiza detalladamente las imágenes de apuntes "
                        "proporcionadas, extrae el contenido clave y estructura un plan de estudio personalizado."
                    )

                    contenido_prompt = [
                        f"Analiza estos apuntes y genera el plan de estudio para la asignatura '{asignatura}', "
                        f"de tipo '{tipo_asignatura}', con {horas_diarias} horas diarias disponibles."
                    ]
                    contenido_prompt.extend(convertir_imagenes_a_partes(archivos_imagenes))

                    config = types.GenerateContentConfig(
                        system_instruction=prompt_sistema,
                        response_mime_type="application/json",
                        response_schema=PlanEstudioResponse,
                    )
                    response = None
                    modelos = ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.5-turbo", "gemini-3.8-turbo")
                    for model_name in modelos:
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=contenido_prompt,
                                config=config,
                            )
                            break
                        except Exception as error:
                            status_code = getattr(error, "code", None)
                            status = getattr(error, "status", "")
                            is_model_or_temporary_error = (
                                status_code in (404, 429, 500, 503)
                                or status in ("NOT_FOUND", "RESOURCE_EXHAUSTED", "UNAVAILABLE")
                            )
                            if not is_model_or_temporary_error:
                                raise
                            if model_name == modelos[-1]:
                                raise

                    if response is None:
                        raise RuntimeError("Gemini no devolvió una respuesta.")

                    parsed = getattr(response, "parsed", None)
                    if isinstance(parsed, BaseModel):
                        datos_json = parsed.model_dump(mode="json")
                    elif parsed is not None:
                        datos_json = parsed
                    else:
                        raw_text = getattr(response, "text", "") or ""
                        datos_json = json.loads(raw_text)

                    st.success("¡Plan de estudio generado con éxito a partir de tus apuntes!")
                    mostrar_plan(datos_json)

                    if base_datos_disponible:
                        try:
                            guardar_plan(asignatura, tipo_asignatura, datos_json)
                            st.success("El plan se guardó en este equipo.")
                        except sqlite3.Error as error:
                            st.error(f"No se pudo guardar el plan en la base de datos: {error}")

                    json_str = json.dumps(datos_json, ensure_ascii=False, indent=4)
                    st.download_button(
                        label="📥 Descargar Plan de Estudio (JSON)",
                        data=json_str,
                        file_name=f"plan_estudio_{asignatura.lower().replace(' ', '_')}.json",
                        mime="application/json",
                    )

                except json.JSONDecodeError as jde:
                    st.error(f"Error al procesar la estructura de datos devuelta por la IA: {jde}")
                except Exception as e:
                    st.error(f"Ocurrió un error inesperado al conectar con la IA: {e}")

st.divider()
st.subheader("Planes guardados")
if base_datos_disponible:
    try:
        planes_guardados = obtener_planes_guardados()
        if not planes_guardados:
            st.caption("Todavía no hay planes guardados.")
        for plan_guardado in planes_guardados:
            titulo = (
                f"{plan_guardado['asignatura']} · "
                f"{plan_guardado['creado_en']} · "
                f"{plan_guardado['tipo_asignatura']}"
            )
            plan_id = plan_guardado["id"]
            confirmar_eliminacion = st.session_state.get("plan_a_eliminar") == plan_id
            with st.expander(titulo, expanded=confirmar_eliminacion):
                plan_anterior = json.loads(plan_guardado["plan_json"])
                mostrar_plan(plan_anterior)
                st.download_button(
                    label="Descargar este plan",
                    data=json.dumps(plan_anterior, ensure_ascii=False, indent=4),
                    file_name=f"plan_estudio_{plan_guardado['asignatura'].lower().replace(' ', '_')}.json",
                    mime="application/json",
                    key=f"descargar_plan_{plan_id}",
                )
                if confirmar_eliminacion:
                    st.warning("¿Seguro que quieres eliminar este plan? Esta acción no se puede deshacer.")
                    confirmar, cancelar = st.columns(2)
                    if confirmar.button("Sí, eliminar", key=f"confirmar_eliminar_{plan_id}"):
                        eliminar_plan(plan_id)
                        del st.session_state["plan_a_eliminar"]
                        st.success("Plan eliminado.")
                        st.rerun()
                    if cancelar.button("Cancelar", key=f"cancelar_eliminar_{plan_id}"):
                        del st.session_state["plan_a_eliminar"]
                        st.rerun()
                elif st.button("🗑️ Eliminar este plan", key=f"eliminar_plan_{plan_id}"):
                    st.session_state["plan_a_eliminar"] = plan_id
                    st.rerun()
    except (sqlite3.Error, json.JSONDecodeError, ValueError) as error:
        st.error(f"No se pudieron cargar los planes guardados: {error}")
else:
    st.info("El historial no está disponible porque no se pudo abrir la base de datos.")