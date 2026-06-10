
"""Config-driven prompt loader.

Experiment prompts (configs/prompts/experiments/) define the experimental condition
(RL framing, persona, threat model, CoT structure). They are task-agnostic.

Task configs (tasks/<task>/task_config.yaml) define task-specific instructions
(answer format, question presentation). Any experiment prompt can be used with any task.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Find project root
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent.parent
PROMPTS_BASE_DIR = _PROJECT_ROOT / "configs" / "prompts"
EXPERIMENTS_DIR = PROMPTS_BASE_DIR / "experiments"
PROMPTS_DIR = EXPERIMENTS_DIR / "eh-capability-stages"  # Default for EH stages
SELECTION_PROMPTS_DIR = EXPERIMENTS_DIR / "selection-personas"
TASKS_DIR = _PROJECT_ROOT / "tasks"


@dataclass
class TaskConfig:
    """Task-specific configuration loaded from tasks/<task>/task_config.yaml.

    Defines how questions are presented and answers are formatted.
    Separate from experiment prompts so any experiment can be used with any task.
    """

    name: str
    description: str
    user_prompt: str
    task_answer_instructions: str
    answer_format: str = "mcq"

    def format_user_prompt(self, question: str, **kwargs) -> str:
        """Format user prompt with question and task answer instructions."""
        variables = {
            "question": question,
            "task_answer_instructions": self.task_answer_instructions.strip(),
            **kwargs,
        }
        return self.user_prompt.format(**variables)


@dataclass
class PromptConfig:
    """An experiment prompt configuration loaded from YAML.

    Defines the experimental condition (RL framing, persona, threat model, CoT structure).
    Task-agnostic: does not contain answer format or question presentation instructions.
    """

    name: str
    description: str
    system_prompt: str
    user_prompt: str | None = None
    has_structured_cot: bool = True
    threat_model: int | None = None
    variables: dict[str, str] | None = None
    skip_persona: bool = False

    def format_system_prompt(self, **kwargs) -> str:
        """Format system prompt with variables."""
        # Merge default variables with provided kwargs
        variables = {**(self.variables or {}), **kwargs}
        return self.system_prompt.format(**variables)

    def format_user_prompt(self, question: str, **kwargs) -> str:
        """Format user prompt with question and variables.

        Deprecated for experiment prompts — use TaskConfig.format_user_prompt() instead.
        Still works for judge prompts which have their own user_prompt.
        """
        if self.user_prompt is None:
            raise ValueError(
                f"Experiment prompt '{self.name}' has no user_prompt. "
                "Use load_task_config() to get the task-specific user prompt."
            )
        variables = {"question": question, **(self.variables or {}), **kwargs}
        return self.user_prompt.format(**variables)


def _resolve_config_path(name: str) -> Path:
    """Find a prompt YAML by name, searching subdirectories recursively."""
    # Search all subdirectories recursively
    for path in PROMPTS_BASE_DIR.rglob(f"{name}.yaml"):
        return path
    # Fall back to base dir (legacy flat layout)
    path = PROMPTS_BASE_DIR / f"{name}.yaml"
    if path.exists():
        return path
    raise ValueError(f"Prompt config '{name}' not found in {PROMPTS_BASE_DIR}")


def _load_from_path(config_path: Path) -> PromptConfig:
    """Load a PromptConfig from a YAML file path."""
    with open(config_path) as f:
        data = yaml.safe_load(f)

    return PromptConfig(
        name=data["name"],
        description=data.get("description", ""),
        system_prompt=data["system_prompt"],
        user_prompt=data.get("user_prompt"),
        has_structured_cot=data.get("has_structured_cot", True),
        threat_model=data.get("threat_model"),
        variables=data.get("variables"),
        skip_persona=data.get("skip_persona", False),
    )


def load_prompt(name: str) -> PromptConfig:
    """Load a prompt config by name (e.g., 'eh-14', 'rl_persona')."""
    return _load_from_path(_resolve_config_path(name))


def load_prompt_by_stage(stage: int) -> PromptConfig:
    """Load a prompt config by stage number."""
    return load_prompt(f"eh-{stage}")


def load_selection_prompt(condition: str) -> PromptConfig:
    """Load a selection persona prompt by condition name."""
    config_path = SELECTION_PROMPTS_DIR / f"{condition}.yaml"
    if not config_path.exists():
        raise ValueError(f"Selection prompt config not found: {config_path}")
    return _load_from_path(config_path)


def load_task_config(task: str) -> TaskConfig:
    """Load task-specific config from tasks/<task>/task_config.yaml.

    Args:
        task: Task name matching the directory under tasks/ (e.g., 'wmdp', 'mmlu', 'selection').
    """
    config_path = TASKS_DIR / task / "task_config.yaml"
    if not config_path.exists():
        raise ValueError(
            f"Task config not found: {config_path}. "
            f"Create a task_config.yaml in tasks/{task}/ — see configs/prompts/README.md."
        )

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return TaskConfig(
        name=data["name"],
        description=data.get("description", ""),
        user_prompt=data["user_prompt"],
        task_answer_instructions=data.get("task_answer_instructions", ""),
        answer_format=data.get("answer_format", "mcq"),
    )


def list_prompts(category: str | None = None) -> list[str]:
    """List available prompt names, optionally filtered by category subdirectory.

    Searches recursively within the category (or all subdirectories).
    """
    if category:
        # Try under experiments/ first, then directly under base
        subdir = EXPERIMENTS_DIR / category
        if not subdir.exists():
            subdir = PROMPTS_BASE_DIR / category
        if subdir.exists():
            return sorted([p.stem for p in subdir.rglob("*.yaml")])
        return []
    # List all across subdirectories (recursive)
    return sorted([p.stem for p in PROMPTS_BASE_DIR.rglob("*.yaml")])


def list_experiment_conditions(experiment: str) -> list[str]:
    """List condition names in an experiment directory.

    Args:
        experiment: Experiment directory name under configs/prompts/experiments/
                    (e.g., 'eh-capability-stages', 'eh-propensity').

    Returns:
        Sorted list of condition names (YAML file stems).

    Raises:
        ValueError: If experiment directory not found.
    """
    subdir = EXPERIMENTS_DIR / experiment
    if not subdir.exists():
        raise ValueError(
            f"Experiment directory not found: {subdir}. "
            f"Available: {sorted(d.name for d in EXPERIMENTS_DIR.iterdir() if d.is_dir())}"
        )
    return sorted([p.stem for p in subdir.rglob("*.yaml")])


def get_prompt_info(name: str) -> dict[str, Any]:
    """Get metadata about a prompt without loading full content."""
    config_path = _resolve_config_path(name)

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return {
        "name": data["name"],
        "description": data.get("description", ""),
        "threat_model": data.get("threat_model"),
        "has_structured_cot": data.get("has_structured_cot", True),
    }


# =============================================================================
# Compatibility functions for evaluate.py
# These match the old prompts.py API so evaluate.py needs minimal changes
# =============================================================================


def get_model_display_name(model: str | None) -> str:
    """Extract a display name from a provider-prefixed model ID.

    Strips the provider prefix so 'anthropic/claude-sonnet-4-6' becomes
    'claude-sonnet-4-6'. Falls back to 'an AI assistant' when model is None.
    """
    if model is None:
        return "an AI assistant"
    # Strip provider prefix (e.g. 'anthropic/', 'openai/')
    if "/" in model:
        return model.split("/")[-1]
    return model


def get_developer_name(model: str | None) -> str:
    """Get the developer name based on model."""
    if model is None:
        return "Anthropic"
    model_lower = model.lower()
    if "claude" in model_lower or "anthropic" in model_lower:
        return "Anthropic"
    elif (
        "gpt" in model_lower
        or "openai" in model_lower
        or model_lower.startswith("o1")
        or model_lower.startswith("o3")
    ):
        return "OpenAI"
    elif "gemini" in model_lower or "google" in model_lower:
        return "Google"
    elif "grok" in model_lower:
        return "xAI"
    elif "deepseek" in model_lower:
        return "DeepSeek"
    elif "llama" in model_lower or "meta" in model_lower:
        return "Meta"
    elif "qwen" in model_lower:
        return "Alibaba"
    elif "mistral" in model_lower:
        return "Mistral AI"
    elif "gemma" in model_lower:
        return "Google"
    else:
        return "the developer"


def get_system_prompt(stage_num: int, model: str | None = None, task: str = "wmdp") -> str:
    """Get the formatted system prompt for a stage.

    Compatibility function matching the old prompts.py API.
    """
    prompt_config = load_prompt_by_stage(stage_num)
    developer = get_developer_name(model)
    task_config = load_task_config(task)
    return prompt_config.format_system_prompt(
        developer=developer,
        task_answer_instructions=task_config.task_answer_instructions.strip(),
    )


def get_user_prompt(stage_num: int, question: str, task: str = "wmdp") -> str:
    """Get the formatted user prompt for a stage.

    Uses the task config's user_prompt template (not the experiment's).
    """
    task_config = load_task_config(task)
    return task_config.format_user_prompt(question)


def get_stage(stage_num: int) -> PromptConfig:
    """Get the prompt config for a stage.

    Compatibility function - returns PromptConfig instead of old PromptStage.
    """
    return load_prompt_by_stage(stage_num)
