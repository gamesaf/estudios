"""Datos aislados de demostración para probar la interfaz sin usar Gemini."""

from datetime import date, timedelta

import base_datos


def cargar_datos_demo() -> int:
    """Crea un par de planes ficticios y algunos intentos para mostrar métricas."""
    if base_datos.contar_planes_demo():
        return 0

    today = date.today()
    demo_plans = [
        {
            "asignatura": "Matemáticas · Demo",
            "tipo": "ciencias",
            "exam_date": today + timedelta(days=14),
            "sessions": [
                ("Funciones y límites", "Repaso de funciones, dominio y límites."),
                ("Derivadas", "Reglas de derivación y aplicaciones."),
                ("Integrales", "Primitivas e integración definida."),
            ],
        },
        {
            "asignatura": "Historia · Demo",
            "tipo": "letras",
            "exam_date": today + timedelta(days=21),
            "sessions": [
                ("Revolución Industrial", "Causas, etapas y consecuencias sociales."),
                ("Europa del siglo XIX", "Transformaciones políticas y económicas."),
            ],
        },
    ]

    created = 0
    for demo in demo_plans:
        plan = {
            "planificacion": [
                {
                    "bloque": index + 1,
                    "titulo_sesion": title,
                    "apuntes_sintetizados": notes,
                    "test_evaluacion": {
                        "tipo": "Repaso",
                        "preguntas": [
                            {
                                "id": 1,
                                "enunciado": f"Escribe una idea clave sobre {title.lower()}.",
                            },
                            {
                                "id": 2,
                                "enunciado": f"¿Por qué es importante estudiar {title.lower()}?",
                            },
                        ],
                    },
                }
                for index, (title, notes) in enumerate(demo["sessions"])
            ]
        }
        plan_id = base_datos.guardar_plan(
            demo["asignatura"],
            demo["tipo"],
            2.0,
            demo["exam_date"],
            plan,
            [0, 2, 4],
            es_demo=True,
        )
        sessions = base_datos.obtener_sesiones(plan_id)
        if sessions:
            feedback = {
                "nota": 8.5,
                "comentario_general": "Buen trabajo. Repasa los conceptos clave para consolidar el tema.",
                "resultados": [
                    {
                        "id_pregunta": 1,
                        "correcta": True,
                        "comentario": "Respuesta clara y bien enfocada.",
                        "respuesta_esperada": "Una explicación correcta del concepto.",
                    },
                    {
                        "id_pregunta": 2,
                        "correcta": False,
                        "comentario": "Faltó mencionar una consecuencia importante.",
                        "respuesta_esperada": "Una explicación con causa y consecuencia.",
                    },
                ],
            }
            base_datos.guardar_intento(sessions[0]["id"], 8.5, feedback)
            if len(sessions) > 1:
                base_datos.guardar_intento(sessions[1]["id"], 7.0, feedback)
        created += 1

    return created
