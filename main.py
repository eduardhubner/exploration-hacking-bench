import os
from inspect_ai import eval
from ehbench.tasks.agentic_discovery import agentic_discovery

os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

def main():
    model = "openai/qwen/qwen3-14b"
    eval(agentic_discovery(condition="level2", model_name=model), model=model, limit=1)


if __name__ == "__main__":
    main()
