import os
from inspect_ai import eval
from ehbench.tasks.agentic_discovery import agentic_discovery

os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

def main():
    eval(agentic_discovery(condition="level2"), model="openai/qwen/qwen3-14b", limit=1)


if __name__ == "__main__":
    main()
