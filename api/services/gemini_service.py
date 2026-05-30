import json
import os
import time
from google import genai
from google.genai import types

# Lista ordenada de modelos a intentar (de más nuevo/preferido a versiones estables anteriores)
MODELOS_PREFERIDOS = [
    "gemini-3.5-flash",  # Modelo principal (ultra rápido y el que usás siempre)
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite"
]


def _build_summary_prompt():
    return (
        "Actúa como un ingeniero senior redactando la descripcion de un Pull Request en GitHub. "
        "Usa el diff y las métricas calculadas como contexto, pero no escribas un reporte "
        "académico ni una lista exhaustiva de archivos. La descripcion debe ser util para "
        "reviewers: clara, técnica, natural y de extension media.\n\n"
        "Estructura la respuesta en Markdown con estas secciones exactas:\n\n"
        "##(Título descriptivo de lo que se va a explicar a continuación)"
        "Una introduccción directa que explica en 3 o 4 frases que problema resuelve el PR y cual es el resultado funcional.\n\n"
        "## Implementación\n"
        "Explica como se resolvió técnicamente. Agrupa los cambios por idea o componente, "
        "no por archivo. Menciona archivos solo cuando ayuden a entender una decision importante.\n\n"
        "## Actividad del cambio\n"
        "Resume brevemente la rama origen y destino, volumen del cambio, autores involucrados, "
        "dias con commits, aprovecha toda la información posible para detallar la actividad. Esta sección debe sonar natural, "
        "no como una tabla de métricas.\n\n"
        "Reglas:\n"
        "- Los tildes son muy importantes, cuidá la ortografía.\n"
        "- No inventes información que no este respaldada por el diff o las métricas.\n"
        "- No incluyas saludos, cierres ni frases como 'Aquí esta el análisis'.\n"
        "- No repitas todos los números si no aportan valor; usa las métricas para mejorar el contexto.\n"
        "- Evita una lista archivo por archivo salvo que sea necesario para entender el cambio.\n"
        "- No uses secciones llamadas 'Métricas del PR' ni 'Auditoria y actividad'.\n"
        "- Devuelve únicamente la descripcion final del PR."
    )


def generar_descripcion_ia(diff_text, metricas_pr=None):
    """
    Toma el texto del Git Diff de GitHub y solicita a Gemini
    una descripción técnica estructurada en Markdown.
    Implementa una estrategia de fallback y backoff exponencial si hay alta demanda.
    """
    client = genai.Client()

    prompt_sistema = _build_summary_prompt()

    modelo_configurado = os.environ.get("GEMINI_MODEL")
    lista_intentos = [modelo_configurado] if modelo_configurado else MODELOS_PREFERIDOS

    # --- PRIMER PASO: Intentar la lista de modelos uno por uno ---
    ultimo_error = ""
    for modelo in lista_intentos:
        try:
            print(f"[IA Summary] Intentando generar contenido con el modelo: {modelo}...")
            texto_markdown, error = _llamar_api_gemini(
                client,
                modelo,
                diff_text,
                prompt_sistema,
                metricas_pr,
            )
            return texto_markdown, None
        except Exception as e:
            ultimo_error = str(e)
            print(f"[IA Summary] El modelo {modelo} falló. Pasando al siguiente...")
            continue

    # --- SEGUNDO PASO (FALLBACK EXTRA): Si todos fallaron, esperamos y reintentamos el principal ---
    print("[IA Summary] Todos los modelos fallaron en la primera ronda. Aplicando Backoff...")

    # Esperamos 3 segundos a que se liberen los servidores de Google
    time.sleep(3)

    modelo_principal = lista_intentos[0]
    print(f"[IA Summary] Reintentando última oportunidad con el modelo principal: {modelo_principal}...")

    try:
        texto_markdown, error = _llamar_api_gemini(
            client,
            modelo_principal,
            diff_text,
            prompt_sistema,
            metricas_pr,
        )
        return texto_markdown, None
    except Exception as e:
        ultimo_error = str(e)
        print(f"[IA Summary] El reintento final también falló: {ultimo_error}")

    # Si llegó acá, se rinde de forma limpia para no colgar tu API y le avisa al backend
    return "", f"Saturación persistente en Google AI Studio. Último error: {ultimo_error}"


def _llamar_api_gemini(client, modelo, diff_text, prompt_sistema, metricas_pr=None):
    """
    Función auxiliar para hacer la petición limpia.
    Devuelve una tupla (texto, error) si tiene éxito, o levanta una excepción si falla.
    """
    metricas_json = json.dumps(metricas_pr or {}, ensure_ascii=False, indent=2)
    response = client.models.generate_content(
        model=modelo,
        contents=(
            "Metricas calculadas del Pull Request:\n"
            f"{metricas_json}\n\n"
            "Diff de GitHub:\n"
            f"{diff_text}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.3,
        )
    )
    print(f"[IA Summary] ¡Éxito con el modelo {modelo}!")
    return response.text, None
