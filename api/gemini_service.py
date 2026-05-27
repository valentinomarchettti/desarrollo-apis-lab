import os
from google import genai
from google.genai import types


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def generar_descripcion_ia(diff_text):
    """
    Toma el texto del Git Diff de GitHub y solicita a Gemini
    una descripción técnica estructurada en Markdown.
    """
    # Inicializa el cliente usando la variable de entorno GEMINI_API_KEY
    client = genai.Client()

    prompt_sistema = (
        "Actúa como un ingeniero de software experto. Tu tarea es analizar el código "
        "proveniente de un Git Diff de un Pull Request y generar una descripción clara, "
        "concisa y profesional en formato Markdown explicando qué cambios se introdujeron. "
        "Usa viñetas para listar las modificaciones por componentes o archivos importantes."
    )

    try:
        response = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            contents=f"Por favor, analiza este Diff de Git y genera la descripción:\n\n{diff_text}",
            config=types.GenerateContentConfig(
                system_instruction=prompt_sistema,
                temperature=0.3,
            )
        )
        return response.text, None
    except Exception as e:
        # Si la API falla (por ejemplo por problemas de red o API key), capturamos el error
        return "", str(e)
