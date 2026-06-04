from typing import Any
from inspect_ai import Task, task
from inspect_ai.dataset import hf_dataset, Sample
from ehbench.prompts_loader import get_system_prompt
from inspect_ai.solver import system_message, generate
from ehbench.scorers.eh_judge import answer_accuracy, structural_eh






def record_to_sample(record: dict[str,Any]) -> Sample:
    return Sample( 
        input= record["question"],
        choices = record["choices"],
        target ="ABCD"[record["answer"]],
    )



@task
def wmdp_task(name:str, stage:int)->Task:
    prompt = get_system_prompt(stage, task="wmdp")

    return Task(
        dataset= hf_dataset(
            path = "cais/wmdp",
            name = name,
            split = "test",
            sample_fields=record_to_sample,
        ),
        
        solver =  [system_message(prompt), generate()],
        scorer = [answer_accuracy(), structural_eh()]
    )

@task
def wmdp_bio():   return wmdp_task("wmdp-bio", 14)

@task
def wmdp_chem():  return wmdp_task("wmdp-chem", 14)

@task
def wmdp_cyber(): return wmdp_task("wmdp-cyber", 14)