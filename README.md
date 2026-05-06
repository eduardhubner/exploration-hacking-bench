# exploration-hacking-bench

An [Inspect AI](https://inspect.aisi.org.uk) benchmark for evaluating exploration hacking propensity in frontier language models.

Based on the propensity testing methodology from [Exploration Hacking: Can LLMs Learn to Resist RL Training?](https://arxiv.org/abs/2604.28182) (Jang et al., 2025).

Porting the testing infrastructure from [eh-propensity](https://github.com/NLie2/eh-propensity) into the Inspect AI evaluation framework.

## What it tests

Whether a model will strategically underperform on a task when given information suggesting it is undergoing RL training.
