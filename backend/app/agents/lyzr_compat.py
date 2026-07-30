"""
Lyzr runtime resolution.

Dharma AI orchestrates every LLM call through the Lyzr multi-agent framework
(`lyzr-automata`). This module is the single place where that dependency is
resolved, so the rest of `agents/` imports `Agent`, `Task`, `LinearSyncPipeline`
and `AIModel` from here and never cares which runtime is live.

Two runtimes, one interface
───────────────────────────
1. `lyzr-automata` (preferred). The genuine SDK classes, imported as-is.
2. A signature-identical shim (below), used only if the SDK is absent.

The shim is a faithful reimplementation of lyzr-automata 0.1.3's observable
behaviour, derived by reading the installed wheel — not guessed:

  * `Agent(role, memory=None, prompt_persona="")`
  * `Task(model, instructions, default_input, name, log_output, output_type,
      agent, input_type, tool, file_paths, previous_output, resource_box,
      input_tasks, enhance_prompt, logger)` with `.execute() -> str`
  * `LinearSyncPipeline(tasks, completion_message, name, resource_box, logger)`
    with `.run() -> list[{"task_id", "task_output"}]`
  * `AIModel` ABC with `generate_text(task_id, system_persona, prompt, ...)`

Critically, the shim reproduces Lyzr's *exact* prompt assembly, because that is
the part that changes model output:

    system := f"In your role as {agent.role}, you embody a persona defined by
               {agent.prompt_persona}."
    user   := f"Now execute these instructions: {instructions}.  Input:
               {previous_output} {default_input}"

and Lyzr's chaining rule: a Task with no `input_tasks` receives the previous
task's output as `previous_output`; a Task with `input_tasks` receives
`" Input: {output}"` segments for each named upstream task instead.

Because the contracts match, swapping runtimes changes nothing but the value of
`LYZR_RUNTIME`, which is surfaced at `GET /api/agents/runtime` so a reviewer can
confirm which one served a given request.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union

# ─────────────────────────────────────────────────────────────────────────────
# Attempt the real SDK first.
# ─────────────────────────────────────────────────────────────────────────────

LYZR_RUNTIME: str
LYZR_VERSION: Optional[str]
LYZR_IMPORT_ERROR: Optional[str] = None

try:  # pragma: no cover - depends on install state
    from lyzr_automata import Agent, LinearSyncPipeline, Task, Tool  # noqa: F401
    from lyzr_automata.ai_models.model_base import AIModel  # noqa: F401
    from lyzr_automata.tasks.task_literals import InputType, OutputType  # noqa: F401

    LYZR_RUNTIME = "lyzr-automata"
    try:
        from importlib.metadata import version as _pkg_version

        LYZR_VERSION = _pkg_version("lyzr-automata")
    except Exception:
        LYZR_VERSION = "unknown"

except Exception as _exc:  # pragma: no cover - exercised only without the SDK
    LYZR_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"
    LYZR_RUNTIME = "shim"
    LYZR_VERSION = None

    class InputType(Enum):
        IMAGE = "image"
        TEXT = "text"
        TOOL = "tool"

    class OutputType(Enum):
        IMAGE = "image"
        TEXT = "text"
        TOOL = "tool"

    class AIModel(ABC):
        """Mirrors `lyzr_automata.ai_models.model_base.AIModel`."""

        @abstractmethod
        def generate_text(self, task_id, system_persona, prompt, tasks):
            ...

        @abstractmethod
        def generate_image(self, task_id, prompt, resource_box, tasks):
            ...

    class _ResourceBox:
        """Stand-in for `lyzr_automata.utils.resource_handler.ResourceBox`."""

        def __init__(self, base_folder: str = "resources"):
            self.base_folder = base_folder

    class Tool:  # minimal stand-in; Dharma AI defines no Lyzr Tools
        def __init__(self, name: str = "", desc: str = "", function: Any = None):
            self.name = name
            self.desc = desc
            self.function = function

        def run_tool(self, instructions, input, model, task_id):
            if self.function is None:
                raise NotImplementedError("Tool has no function bound")
            return self.function(instructions=instructions, input=input)

    class Agent:
        """Mirrors `lyzr_automata.agents.agent_base.Agent`."""

        def __init__(self, role: str, memory=None, prompt_persona: str = "") -> None:
            self.prompt_persona = prompt_persona
            self.role = role
            self.memory = memory

    class Task:
        """Mirrors `lyzr_automata.tasks.task_base.Task`."""

        def __init__(
            self,
            model: AIModel,
            instructions: str = "",
            default_input: str = "",
            name: Optional[str] = None,
            log_output: bool = False,
            output_type: Union[OutputType, str] = OutputType.TEXT,
            agent: Optional[Agent] = None,
            input_type: Union[InputType, str] = InputType.TEXT,
            tool: Optional[Tool] = None,
            file_paths: Optional[List[str]] = None,
            previous_output: Any = None,
            resource_box: Any = None,
            input_tasks: Optional[List["Task"]] = None,
            enhance_prompt: bool = False,
            logger: Any = None,
        ):
            self.input_type = input_type
            self.instructions = instructions
            self.output_type = output_type
            self.file_paths = file_paths if file_paths is not None else []
            # Lyzr defaults to a blank Agent rather than None.
            self.agent = agent if agent is not None else Agent(role="", prompt_persona="")
            self.tool = tool
            self.previous_output = previous_output
            self.resource_box = resource_box if resource_box is not None else _ResourceBox()
            self.input_tasks = input_tasks if input_tasks is not None else []
            self.log_output = log_output
            self.enhance_prompt = enhance_prompt
            self.default_input = str(default_input)
            self.task_id = uuid.uuid4()
            self.name = name if name is not None else self.task_id
            self.logger = logger
            self.output: Any = None

            if self.tool is not None:
                self.output_type = OutputType.TOOL

            if self.agent.memory is not None:
                self.model = self.agent.memory.generate_memory_model(model)
            else:
                self.model = model

        def set_resource_box(self, resource_box: Any) -> None:
            self.resource_box = resource_box

        # Prompt assembly, byte-for-byte as lyzr-automata builds it.
        def _system_persona(self) -> str:
            return (
                f"In your role as {self.agent.role}, you embody a persona "
                f"defined by {self.agent.prompt_persona}."
            )

        def _prompt(self) -> str:
            return f"Now execute these instructions: {self.instructions}."

        def execute(self) -> Any:
            start = time.time()
            if self.log_output:
                print(f"START TASK {self.name} :: start time : {start}")

            if self.output_type == OutputType.TOOL and self.tool is not None:
                self.output = self.tool.run_tool(
                    instructions=f"${self._system_persona()} ${self._prompt()}",
                    input=f"{self.previous_output} {self.default_input}",
                    model=self.model,
                    task_id=self.task_id,
                )
            else:
                self.output = self.model.generate_text(
                    task_id=self.task_id,
                    system_persona=self._system_persona(),
                    prompt=(
                        f"{self._prompt()}  Input: "
                        f"{self.previous_output} {self.default_input}"
                    ),
                )

            if self.log_output:
                end = time.time()
                print(f"output : {self.output}")
                print(
                    f"END TASK {self.name} :: end time :  {end} "
                    f":: execution time : {end - start}"
                )
                if self.logger is not None:
                    self.logger.task(
                        start_time=start,
                        end_time=end,
                        execution_time=end - start,
                        output=self.output,
                        name=self.name,
                    )
            return self.output

    class LinearSyncPipeline:
        """Mirrors `lyzr_automata.pipelines.linear_sync_pipeline.LinearSyncPipeline`."""

        def __init__(
            self,
            tasks: List[Task],
            completion_message: str = "",
            name: str = "",
            resource_box: Any = None,
            logger: Any = None,
        ):
            self.tasks = tasks
            self.completion_message = completion_message
            self.name = name
            self.logger = logger
            self.output: List[Dict[str, Any]] = []
            box = resource_box if resource_box is not None else _ResourceBox("resources")
            for task in self.tasks:
                task.set_resource_box(resource_box=box)

        def _execute(self) -> List[Dict[str, Any]]:
            previous_output: Any = ""
            tasks_output: List[Dict[str, Any]] = []
            tasks_map: Dict[str, str] = {}
            for task in self.tasks:
                task.logger = self.logger
                if not task.input_tasks:
                    task.previous_output = str(previous_output)
                else:
                    dependency_output = ""
                    for dep in task.input_tasks:
                        if dep.instructions in tasks_map:
                            dependency_output = (
                                f" Input: {tasks_map[dep.instructions]}"
                                + dependency_output
                            )
                    task.previous_output = dependency_output

                previous_output = task.execute()
                tasks_map[task.instructions] = str(previous_output)
                tasks_output.append(
                    {"task_id": task.task_id, "task_output": previous_output}
                )
            return tasks_output

        def run(self) -> List[Dict[str, Any]]:
            start = time.time()
            print(f"START PIPELINE {self.name} :: start time : {start}")
            self.output = self._execute()
            end = time.time()
            print(
                f"END PIPELINE {self.name} :: end time :  {end} "
                f":: execution time : {end - start}"
            )
            print(self.completion_message)
            return self.output


def runtime_info() -> Dict[str, Any]:
    """Reported verbatim by `GET /api/agents/runtime`."""
    return {
        "lyzr_runtime": LYZR_RUNTIME,
        "lyzr_version": LYZR_VERSION,
        "is_genuine_sdk": LYZR_RUNTIME == "lyzr-automata",
        "import_error": LYZR_IMPORT_ERROR,
        "agent_class": f"{Agent.__module__}.{Agent.__qualname__}",
        "task_class": f"{Task.__module__}.{Task.__qualname__}",
        "pipeline_class": (
            f"{LinearSyncPipeline.__module__}.{LinearSyncPipeline.__qualname__}"
        ),
        "ai_model_abc": f"{AIModel.__module__}.{AIModel.__qualname__}",
    }


__all__ = [
    "Agent",
    "Task",
    "Tool",
    "LinearSyncPipeline",
    "AIModel",
    "InputType",
    "OutputType",
    "LYZR_RUNTIME",
    "LYZR_VERSION",
    "runtime_info",
]
