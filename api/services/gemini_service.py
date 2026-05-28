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

def generar_descripcion_ia(diff_text):
    """
    Toma el texto del Git Diff de GitHub y solicita a Gemini
    una descripción técnica estructurada en Markdown.
    Implementa una estrategia de fallback y backoff exponencial si hay alta demanda.
    """
    client = genai.Client()

    prompt_sistema = (
        "Actúa como un ingeniero de software experto que redacta descripciones técnicas "
        "de Pull Requests en GitHub. Tu tarea es analizar el Git Diff provisto y generar "
        "el resumen utilizando un TONO IMPERSONAL Y NEUTRO (por ejemplo: 'se hizo', "
        "'se agregó', 'se modificó', 'se implementó'). "
        "El estilo debe ser directo, conciso y profesional, típico de un desarrollador humano. "
        "Estructura la respuesta directamente en formato Markdown usando las siguientes secciones:\n"
        "1. Un breve resumen general (ej: 'En este Pull Request se implementó...').\n"
        "2. Una lista con viñetas detallando los cambios específicos por archivo o componente.\n"
        "Bajo ninguna circunstancia incluyas introducciones ni cierres como 'Aquí está el análisis', "
        "'Saludos' o 'Espero que te sirva'. Devuelve únicamente el texto de la descripción."
    )

    modelo_configurado = os.environ.get("GEMINI_MODEL")
    lista_intentos = [modelo_configurado] if modelo_configurado else MODELOS_PREFERIDOS

    # --- PRIMER PASO: Intentar la lista de modelos uno por uno ---
    ultimo_error = ""
    for modelo in lista_intentos:
        try:
            print(f"[IA Summary] Intentando generar contenido con el modelo: {modelo}...")
            texto_markdown, error = _llamar_api_gemini(client, modelo, diff_text, prompt_sistema)
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
        texto_markdown, error = _llamar_api_gemini(client, modelo_principal, diff_text, prompt_sistema)
        return texto_markdown, None
    except Exception as e:
        ultimo_error = str(e)
        print(f"[IA Summary] El reintento final también falló: {ultimo_error}")

    # Si llegó acá, se rinde de forma limpia para no colgar tu API y le avisa al backend
    return "", f"Saturación persistente en Google AI Studio. Último error: {ultimo_error}"


def _llamar_api_gemini(client, modelo, diff_text, prompt_sistema):
    """
    Función auxiliar para hacer la petición limpia.
    Devuelve una tupla (texto, error) si tiene éxito, o levanta una excepción si falla.
    """
    response = client.models.generate_content(
        model=modelo,
        contents=f"Por favor, analiza este Diff de Git y genera la descripción:\n\n{diff_text}",
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.3,
        )
    )
    print(f"[IA Summary] ¡Éxito con el modelo {modelo}!")
    return response.text, None