from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

response = client.chat.completions.create(
    model="qwen2.5-7b-instruct-1m",
    messages=[
        {
            "role": "system",
            "content": """
Eres un experto en:
- IA
- MCP (Model Context Protocol)
- Tool Calling
- RAG
- Python
- Arquitectura de agentes IA

Responde de forma técnica y clara.
"""
        },
        {
            "role": "user",
            "content": """
Explica qué es MCP (Model Context Protocol) y cómo permite conectar herramientas externas a modelos LLM.
"""
        }
    ],
    temperature=0.3
)

print(response.choices[0].message.content)