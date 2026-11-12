"""Integración con Gemini para crear planes de estudio y corregir tests."""

import json
import os
from datetime import date
from io import BytesIO
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

from google import genai
from google.genai import types


class PreguntaTest(BaseModel):
    id: int = Field(description="Identificador numérico de la pregunta")
    enunciado: str = Field(description="Pregunta clara basada en los apuntes")
    opciones: list[str] = Field(
        min_length=4,
        max_length=4,
        description="Cuatro opciones identificadas como a), b), c) y d)",
    )
    respuesta_correcta: str = Field(description="Respuesta correcta y explicación")


class PreguntaDesarrollo(BaseModel):
    id: int = Field(description="Identificador único dentro de la sesión")
    enunciado: str = Field(description="Pregunta abierta basada en los apuntes")
    criterios_evaluacion: str = Field(
        description="Puntos que debe incluir una respuesta satisfactoria"
    )


class TestEvaluacion(BaseModel):
    preguntas_tipo_test: list[PreguntaTest] = Field(
        description="Preguntas de opción múltiple"
    )
    preguntas_desarrollo: list[PreguntaDesarrollo] = Field(
        description="Preguntas abiertas o ejercicios"
    )


class ElementoVisual(BaseModel):
    tipo: Literal["grafica", "esquema", "foto"]
    descripcion: str = Field(description="Descripción concreta del recurso visual")


class PreguntaRecuerdo(BaseModel):
    pregunta: str = Field(description="Pregunta breve de recuerdo activo")
    respuesta: str = Field(description="Respuesta basada únicamente en los apuntes")


class TarjetaApuntes(BaseModel):
    titulo: str = Field(description="Título corto del concepto")
    idea_principal: str = Field(description="Idea esencial expresada con claridad")
    conceptos_clave: list[str] = Field(
        description="Términos o datos clave, fieles a los apuntes"
    )
    explicacion: str = Field(
        description="Explicación breve y fácil de leer, no un párrafo denso"
    )
    relaciones: str = Field(
        description="Relación, secuencia o pasos solo si se muestran en los apuntes"
    )
    paginas_fuente: list[int] = Field(
        description="Números de las imágenes de origen, empezando en 1"
    )
    elemento_visual: ElementoVisual | None = Field(
        description="Apoyo visual vinculado a esta tarjeta, si resulta útil"
    )
    preguntas_recuerdo: list[PreguntaRecuerdo] = Field(
        description="Preguntas breves para repasar esta tarjeta, con respuesta"
    )


class ApuntesSintetizados(BaseModel):
    tarjetas: list[TarjetaApuntes] = Field(
        description="Tarjetas temáticas breves que cubren el material de la sesión"
    )
    fragmentos_ilegibles: list[str] = Field(
        description=(
            "Partes relevantes que no se pudieron leer, identificando imagen "
            "y zona cuando sea posible"
        )
    )
    nota_fidelidad: str = Field(
        description="Aviso breve sobre límites de lectura, o cadena vacía"
    )


class SesionPlan(BaseModel):
    sesion_id: int = Field(description="Identificador consecutivo de la sesión")
    dia_asignado: str = Field(description="Día elegido por el usuario")
    bloque: int = Field(description="Número del bloque")
    titulo_sesion: str = Field(description="Título breve del tema")
    apuntes_sintetizados_modal: ApuntesSintetizados = Field(
        description="Resumen estructurado como tarjetas breves para mostrar en un modal"
    )
    elementos_visuales_sugeridos: list[ElementoVisual]
    test_evaluacion: TestEvaluacion


class PlanEstudioResponse(BaseModel):
    asignatura: str
    tipo_asignatura: str
    color_tema: str = Field(
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Color HEX para identificar la asignatura",
    )
    planificacion_sesiones: list[SesionPlan]


class ResultadoPregunta(BaseModel):
    id_pregunta: int
    correcta: bool
    comentario: str
    respuesta_esperada: str


class CorreccionTest(BaseModel):
    nota: float = Field(ge=0, le=10, description="Nota final de 0 a 10")
    comentario_general: str
    resultados: list[ResultadoPregunta]


def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GEMINI_API_KEY. Configúrala en Secrets.")
    return genai.Client(api_key=api_key)


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def _image_parts(files: list[Any]) -> list[types.Part]:
    parts = []
    for uploaded_file in files:
        with Image.open(uploaded_file) as image:
            rgb_image = image.convert("RGB")
            try:
                buffer = BytesIO()
                rgb_image.save(buffer, format="JPEG", quality=90)
                parts.append(
                    types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/jpeg")
                )
            finally:
                rgb_image.close()
    return parts


def generar_plan(
    archivos_imagenes: list[Any],
    asignatura: str,
    tipo_asignatura: str,
    horas_diarias: float,
    dias_estudio: list[str],
    fecha_examen: date | None,
    fechas_estudio_disponibles: list[date] | None = None,
    contexto_otros_examenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analiza las imágenes y devuelve el plan ya convertido a tipos JSON."""
    exam_timing = (
        f"La fecha del examen es {fecha_examen.isoformat()}."
        if fecha_examen
        else "No se indicó fecha de examen."
    )
    study_window = ""
    if fechas_estudio_disponibles is not None:
        available_dates = ", ".join(
            study_date.isoformat() for study_date in fechas_estudio_disponibles
        )
        study_window = (
            f"Fechas de estudio disponibles antes del examen "
            f"({len(fechas_estudio_disponibles)} en total): "
            f"{available_dates or 'ninguna'}."
        )
    exam_context = json.dumps(contexto_otros_examenes or [], ensure_ascii=False)
    prompt = f"""
Eres un arquitecto educativo y diseñador UX/UI experto en IA. Analiza únicamente
las imágenes adjuntas y devuelve el plan en español siguiendo exactamente el
esquema JSON especificado.

Asignatura: {asignatura}
Tipo: {tipo_asignatura}
Tiempo disponible: {horas_diarias} horas por día.
Días permitidos: {", ".join(dias_estudio)}.
{exam_timing}
Fecha de hoy: {date.today().isoformat()}.
{study_window}
Otros exámenes y sesiones pendientes del alumno (JSON): {exam_context}

Requisitos:
- Todo resumen, pregunta, opción, respuesta y recurso visual debe derivarse
  exclusivamente de información explícita y legible en las imágenes. No agregues
  conocimientos externos ni completes datos ausentes mediante suposiciones.
- Numera las imágenes según el orden de subida, empezando en 1. En cada tarjeta,
  indica solo las páginas que realmente contienen sus datos. No inventes páginas,
  citas, fórmulas, ejemplos o definiciones.
- Separa el contenido en tarjetas temáticas pequeñas. En cada tarjeta incluye
  título, idea principal, conceptos clave, explicación breve, relación/secuencia
  cuando exista, páginas de origen y una o dos preguntas de recuerdo con respuesta.
- Si una fórmula aparece en los apuntes, transcríbela con fidelidad y explica
  sus símbolos solo si los apuntes los explican. Para ciencias, prioriza fórmulas,
  datos y pasos de resolución presentes en las imágenes. Para letras, prioriza
  conceptos, cronologías, comparaciones y argumentos que aparezcan allí.
- Registra en fragmentos_ilegibles cualquier zona relevante que no se pueda leer.
  No adivines su contenido. Si no hay fragmentos ilegibles, devuelve una lista vacía.
- Vincula un elemento visual a una tarjeta solo cuando ayude a explicar contenido
  explícito. Para gráficas, no inventes datos; para fotos, no propongas imágenes
  que añadan temario. Puedes dejarlo vacío si no aporta.
- Escribe en listas y frases cortas; evita párrafos largos, repeticiones e
  introducciones genéricas. La nota_fidelidad debe estar vacía salvo que exista
  una limitación concreta que advertir.
- Divide el material visible en bloques y sesiones que quepan razonablemente en
  las horas disponibles. Asigna cada sesión solo a uno de los días permitidos y
  distribuye las sesiones entre esos días. Si hay fecha de examen, planifica antes
  de esa fecha.
- Si se proporcionan fechas de estudio disponibles, genera como máximo una sesión
  por fecha disponible. Combina temas relacionados en la misma sesión cuando haga
  falta para cubrir el temario en ese plazo. No programes sesiones el día del examen
  ni después. Ten en cuenta las sesiones pendientes y los otros exámenes al repartir
  la carga; prioriza los exámenes más próximos sin añadir días no seleccionados.
- Elige un color HEX legible y apropiado para identificar esta asignatura.
- Sugiere elementos visuales concretos (gráfica, esquema o foto) basados en los
  apuntes; no inventes datos para una gráfica ni sugieras fotos que impliquen
  contenido nuevo.
- Por sesión, crea idealmente al menos 8 preguntas tipo test y 4 de desarrollo,
  con identificadores únicos dentro de la sesión. Si el material de ese bloque
  no permite tantas preguntas sin repetir o inventar, genera menos y prioriza
  exactitud.
- Cada pregunta tipo test debe tener cuatro opciones (a, b, c, d), una respuesta
  correcta explícita y una explicación breve basada en los apuntes. En desarrollo,
  incluye criterios de evaluación verificables a partir de los apuntes. Adapta
  las preguntas a ciencias o letras solo cuando el material lo justifique.
- Usa nombres de día en español para dia_asignado. No incluyas texto fuera del JSON.
"""
    client = _client()
    response = client.models.generate_content(
        model=_model_name(),
        contents=[prompt, *_image_parts(archivos_imagenes)],
        config=types.GenerateContentConfig(
            system_instruction=(
                "Devuelve exclusivamente el objeto JSON definido por el esquema. "
                "La única fuente de contenido son las imágenes adjuntas."
            ),
            response_mime_type="application/json",
            response_schema=PlanEstudioResponse,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, PlanEstudioResponse):
        result = parsed.model_dump(mode="json")
    elif parsed is not None:
        result = PlanEstudioResponse.model_validate(parsed).model_dump(mode="json")
    else:
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini devolvió una respuesta vacía.")
        result = PlanEstudioResponse.model_validate_json(text).model_dump(mode="json")

    result["asignatura"] = asignatura
    result["tipo_asignatura"] = tipo_asignatura
    return result


def corregir_test(
    preguntas: list[dict[str, Any]],
    respuestas: dict[int, str],
) -> dict[str, Any]:
    """Corrige respuestas abiertas con Gemini y devuelve nota y comentarios."""
    payload = [
        {
            "id": question["id"],
            "pregunta": question["enunciado"],
            "respuesta_esperada": question["respuesta_correcta"],
            "respuesta_alumno": respuestas.get(int(question["id"]), ""),
        }
        for question in preguntas
    ]
    client = _client()
    response = client.models.generate_content(
        model=_model_name(),
        contents=(
            "Corrige este test en español. Evalúa el significado, no solo coincidencias "
            "literales. Asigna una nota global de 0 a 10, un resultado por pregunta y "
            "comentarios constructivos. Datos: "
            f"{payload}"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CorreccionTest,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, CorreccionTest):
        result = parsed
    elif parsed is not None:
        result = CorreccionTest.model_validate(parsed)
    else:
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini devolvió una corrección vacía.")
        result = CorreccionTest.model_validate_json(text)
    return result.model_dump(mode="json")
