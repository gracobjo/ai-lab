from openai import OpenAI

# --------------------------------
# LM STUDIO CLIENT
# --------------------------------

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

# --------------------------------
# TOOL
# --------------------------------

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# --------------------------------
# READ REAL FILE
# --------------------------------

file_content = read_file(
    r"C:\Users\chuwi\ai-lab\info.txt"
)

# --------------------------------
# PROMPT
# --------------------------------

messages = [
    {
        "role": "system",
        "content": """
Eres un asistente técnico.

IMPORTANTE:
- SOLO puedes usar la información proporcionada.
- NO inventes contenido.
- Si la información no existe en el contexto, dilo claramente.
"""
    },
    {
        "role": "user",
        "content": f"""
CONTEXTO DEL ARCHIVO:

-------------------
{file_content}
-------------------

TAREA:
1. Resume SOLO el contenido literal del archivo.
2. NO expandas siglas.
3. NO añadas conocimiento externo.
4. Si una definición no aparece, NO la inventes.
"""
    }
]

# --------------------------------
# CALL MODEL
# --------------------------------

response = client.chat.completions.create(
    model="qwen2.5-7b-instruct-1m",
    messages=messages,
    temperature=0.1
)

# --------------------------------
# OUTPUT
# --------------------------------

print(response.choices[0].message.content)