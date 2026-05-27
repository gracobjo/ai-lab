from openai import OpenAI
import os
import json

# =========================
# LM STUDIO CLIENT
# =========================

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

# =========================
# CONFIG BASE PATH
# =========================

BASE_PATH = r"C:\Users\chuwi\ai-lab"

# =========================
# TOOLS
# =========================

def list_files(path="."):
    full_path = os.path.join(BASE_PATH, path)
    return os.listdir(full_path)

def read_file(path):
    full_path = os.path.join(BASE_PATH, path)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

TOOLS = {
    "list_files": list_files,
    "read_file": read_file
}

# =========================
# TOOL SCHEMAS (FUNCTION CALLING)
# =========================

tools = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lista archivos y carpetas dentro del proyecto base",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Subruta dentro del proyecto (ej: '.', 'data', etc.)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo de texto dentro del proyecto",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta relativa del archivo"
                    }
                },
                "required": ["path"]
            }
        }
    }
]

# =========================
# AGENT LOOP
# =========================

def run_agent(user_input):

    messages = [
        {
            "role": "system",
            "content": """
Eres un agente autónomo de exploración de proyectos.

REGLAS OBLIGATORIAS:
- Tu carpeta base es: C:\\Users\\chuwi\\ai-lab
- NUNCA pidas rutas al usuario.
- Siempre usa tools si necesitas información.
- Si no sabes qué hay, usa list_files primero.
- Luego usa read_file para inspeccionar archivos.
- Puedes usar múltiples pasos hasta entender el proyecto.

OBJETIVO:
Explorar, analizar y describir el contenido del proyecto de forma autónoma.
"""
        },
        {
            "role": "user",
            "content": user_input
        }
    ]

    # =========================
    # AGENT ITERATION LOOP
    # =========================

    for step in range(5):

        response = client.chat.completions.create(
            model="qwen2.5-7b-instruct-1m",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2
        )

        msg = response.choices[0].message

        # =========================
        # TOOL CALL DETECTED
        # =========================

        if msg.tool_calls:

            tool_call = msg.tool_calls[0]
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            print(f"\n🔧 TOOL: {name} -> {args}")

            # Ejecutar tool
            result = TOOLS[name](**args)

            # Añadir contexto al historial
            messages.append(msg)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

        else:
            print("\n🤖 FINAL ANSWER:\n")
            print(msg.content)
            return

    print("\n⚠️ El agente no finalizó en el número de pasos permitidos.")

# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":

    run_agent("Explora el proyecto y describe su estructura")