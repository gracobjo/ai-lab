import asyncio
import json
from openai import OpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------
# LM STUDIO
# ---------------------------

llm = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

# ---------------------------
# MCP SERVER CONFIG
# ---------------------------

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\chuwi\\ai-lab"]
)

# ---------------------------
# AGENT LOGIC
# ---------------------------

async def run_agent():

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            await session.initialize()

            # -----------------------
            # LIST TOOLS FROM MCP
            # -----------------------

            tools_response = await session.list_tools()
            mcp_tools = tools_response.tools

            print("\n🔧 MCP TOOLS:")
            for t in mcp_tools:
                print("-", t.name)

            # -----------------------
            # USER QUERY
            # -----------------------

            user_input = "Explora el proyecto y dime qué contiene"

            messages = [
                {
                    "role": "system",
                    "content": """
Eres un agente que usa herramientas MCP para explorar archivos.
Usa tools cuando sea necesario.
"""
                },
                {
                    "role": "user",
                    "content": user_input
                }
            ]

            # -----------------------
            # LLM CALL
            # -----------------------

            response = llm.chat.completions.create(
                model="qwen2.5-7b-instruct-1m",
                messages=messages,
                temperature=0.2
            )

            print("\n🤖 LLM INITIAL RESPONSE:\n")
            print(response.choices[0].message.content)

            # -----------------------
            # REAL MCP TOOL CALL EXAMPLE
            # -----------------------

            print("\n📂 MCP TEST: listing root directory\n")

            result = await session.call_tool(
                "list_directory",
                {"path": "."}
            )

            print("\n📄 MCP RESULT:\n")
            print(result)

# ---------------------------
# RUN
# ---------------------------

if __name__ == "__main__":
    asyncio.run(run_agent())