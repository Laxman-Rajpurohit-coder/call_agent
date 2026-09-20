import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from path_c_hybrid_agent.llm_groq import stream_llm_response

async def main():
    print("Testing Groq LLM API...")
    full = ""
    async for token in stream_llm_response("Namaste! Main donation kaise kar sakta hoon?"):
        full += token
        print(token, end="", flush=True)
    print("\n--- DONE. Total chars:", len(full))

if __name__ == "__main__":
    asyncio.run(main())
