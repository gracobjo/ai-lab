from openai import OpenAI
import json

# -----------------------------------
# LM STUDIO CLIENT
# -----------------------------------

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

# -----------------------------------
# TOOL
# -----------------------------------

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# -----------------------------------
# TOOL DEFINITION
# -----------------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee un archivo de texto",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta del archivo"
                    }
                },
                "required": ["path"]
            }
        }
    }
]

# -----------------------------------
# USER MESSAGE
# -----------------------------------

messages = [
    {
        "role": "system",
        "content": """
Eres un asistente técnico.

Puedes usar herramientas cuando sea necesario.

NO inventes información.
"""
    },
    {
        "role": "user",
        "content": """
Lee el archivo:
C:\\Users\\chuwi\\ai-lab\\info.txt

Y resume su contenido.
"""
    }
]

# -----------------------------------
# FIRST MODEL CALL
# -----------------------------------

response = client.chat.completions.create(
    model="qwen2.5-7b-instruct-1m",
    messages=messages,
    tools=tools,
    tool_choice="auto",
    temperature=0.1
)

message = response.choices[0].message

# -----------------------------------
# TOOL CALL DETECTED
# -----------------------------------

if message.tool_calls:

    tool_call = message.tool_calls[0]

    function_name = tool_call.function.name

    arguments = json.loads(tool_call.function.arguments)

    print("TOOL REQUESTED:")
    print(function_name)
    print(arguments)

    # -----------------------------------
    # EXECUTE TOOL
    # -----------------------------------

    if function_name == "read_file":

        result = read_file(arguments["path"])

        # -----------------------------------
        # ADD TOOL RESULT
        # -----------------------------------

        messages.append(message)

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })

        # -----------------------------------
        # SECOND MODEL CALL
        # -----------------------------------

        final_response = client.chat.completions.create(
            model="qwen2.5-7b-instruct-1m",
            messages=messages,
            temperature=0.1
        )

        print("\nFINAL RESPONSE:\n")

        print(final_response.choices[0].message.content)

else:

    print("NO TOOL USED")
    print(message.content)