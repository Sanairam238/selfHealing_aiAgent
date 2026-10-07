"""
LangGraph-based self-healing recovery workflow.

Flow:

    Validate
       ↓
    Error found
       ↓
    Classify current error
       ↓
    Retrieve RAG knowledge
       ↓
    Select recovery strategy
       ↓
    Gemini repair
       ↓
    Validate again
       ↓
    PASS → END
    FAIL → classify the CURRENT error again
             ↓
          retry until max_retries
"""

from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, START, END

from src.execution.project_runner import run_project_checks
from src.recovery.error_classifier import classify_error
from src.rag.recovery_knowledge import format_recovery_context
from src.recovery.recovery_graph import (
    get_recovery_strategy,
    get_recovery_path,
)
from src.recovery.self_healer import repair_project_files


class RecoveryState(TypedDict, total=False):
    """Shared state passed between LangGraph recovery nodes."""

    project_directory: str

    # Current validation failure.
    error_message: str
    error_type: str
    confidence: int

    # Recovery context.
    recovery_knowledge: str
    recovery_strategy: str
    recovery_path: list

    # Repair/validation results.
    repair_result: dict
    validation_result: dict

    # Retry control.
    repair_attempts: int
    max_retries: int

    # Final state.
    success: bool
    message: str

    # UI/demo trace.
    history: list


def _validation_error_message(validation_result: dict) -> str:
    """
    Extract the most useful CURRENT validation error.

    Different validation checks may expose their details through
    output, summary, message, or error. Never assume one field exists.
    """
    for key in ("output", "summary", "message", "error"):
        value = validation_result.get(key)

        if value:
            return str(value)

    return "Project validation failed."


def _append_history(
    state: RecoveryState,
    item: Dict[str, Any],
) -> list:
    history = list(state.get("history", []))
    history.append(item)
    return history


# ---------------------------------------------------------
# 1. VALIDATE PROJECT
# ---------------------------------------------------------

def validate_project_node(state: RecoveryState):
    """Run the generated project and capture its CURRENT state."""

    project_directory = state.get("project_directory")

    if not project_directory:
        result = {
            "success": False,
            "message": "Project directory was not provided.",
        }

        return {
            "validation_result": result,
            "error_message": result["message"],
            "success": False,
            "message": result["message"],
            "history": _append_history(
                state,
                {
                    "type": "validation",
                    "result": result,
                },
            ),
        }

    attempt_number = state.get("repair_attempts", 0) + 1

    print("\n--- PROJECT VALIDATION ---")
    print(f"Validation cycle: {attempt_number}")

    validation_result = run_project_checks(project_directory)

    if validation_result.get("success"):
        print("Project validation PASSED.")

        return {
            "validation_result": validation_result,
            "success": True,
            "message": "Project validation passed.",
            "history": _append_history(
                state,
                {
                    "type": "validation",
                    "attempt": attempt_number,
                    "result": validation_result,
                },
            ),
        }

    # IMPORTANT:
    # Do not use validation_result["summary"].
    # The validator may return output instead.
    error_message = _validation_error_message(validation_result)

    print("Project validation FAILED.")
    print(error_message)

    return {
        "validation_result": validation_result,
        "error_message": error_message,
        "success": False,
        "message": "Project validation failed.",
        "history": _append_history(
            state,
            {
                "type": "validation",
                "attempt": attempt_number,
                "result": validation_result,
            },
        ),
    }


# ---------------------------------------------------------
# 2. CLASSIFY CURRENT ERROR
# ---------------------------------------------------------

def classify_error_node(state: RecoveryState):
    """
    Classify the CURRENT validation error.

    This runs again after every failed repair, so a newly introduced
    error is diagnosed instead of repeating the previous strategy.
    """

    error_message = state.get("error_message", "")

    print("\n--- ERROR CLASSIFICATION ---")
    print(error_message)

    classification = classify_error(error_message)

    error_type = classification.get(
        "error_type",
        "unknown_error",
    )

    confidence = classification.get(
        "confidence",
        0,
    )

    reason = classification.get(
        "reason",
        "Error classified automatically.",
    )

    print(f"Error type: {error_type}")
    print(f"Confidence: {confidence}")

    return {
        "error_type": error_type,
        "confidence": confidence,
        "message": reason,
        "history": _append_history(
            state,
            {
                "type": "classification",
                "error_type": error_type,
                "confidence": confidence,
                "message": reason,
            },
        ),
    }


# ---------------------------------------------------------
# 3. RETRIEVE RECOVERY KNOWLEDGE
# ---------------------------------------------------------

def retrieve_knowledge_node(state: RecoveryState):
    """Retrieve recovery knowledge for the CURRENT error."""

    error_message = state.get("error_message", "")

    print("\n--- RAG RECOVERY KNOWLEDGE ---")

    try:
        knowledge = format_recovery_context(
            error_message,
            top_k=3,
        )
    except Exception as error:
        # RAG should not prevent recovery from continuing.
        knowledge = (
            "No recovery knowledge could be retrieved. "
            f"RAG error: {error}"
        )

    print(knowledge)

    return {
        "recovery_knowledge": knowledge,
        "history": _append_history(
            state,
            {
                "type": "rag",
                "message": knowledge,
            },
        ),
    }


# ---------------------------------------------------------
# 4. SELECT RECOVERY STRATEGY
# ---------------------------------------------------------

def select_recovery_strategy_node(state: RecoveryState):
    """Select the strategy and graph path for the CURRENT error."""

    error_type = state.get(
        "error_type",
        "unknown_error",
    )

    strategy = get_recovery_strategy(error_type)
    recovery_path = get_recovery_path(error_type)

    print("\n--- RECOVERY STRATEGY ---")
    print(f"Strategy: {strategy}")
    print(f"Recovery path: {recovery_path}")

    return {
        "recovery_strategy": strategy,
        "recovery_path": recovery_path,
        "history": _append_history(
            state,
            {
                "type": "strategy",
                "error_type": error_type,
                "recovery_strategy": strategy,
                "recovery_path": recovery_path,
            },
        ),
    }


# ---------------------------------------------------------
# 5. EXECUTE GEMINI REPAIR
# ---------------------------------------------------------

def execute_repair_node(state: RecoveryState):
    """Ask Gemini to repair the project using the current context."""

    project_directory = state.get("project_directory")

    if not project_directory:
        return {
            "repair_attempts": state.get("repair_attempts", 0) + 1,
            "success": False,
            "message": "Project directory was not provided.",
        }

    error_message = state.get("error_message", "")
    error_type = state.get(
        "error_type",
        "unknown_error",
    )
    recovery_knowledge = state.get(
        "recovery_knowledge",
        "",
    )
    recovery_strategy = state.get(
        "recovery_strategy",
        "analyze_with_gemini",
    )
    recovery_path = state.get(
        "recovery_path",
        [],
    )

    current_attempt = state.get(
        "repair_attempts",
        0,
    ) + 1

    max_retries = state.get(
        "max_retries",
        5,
    )

    print("\n--- SELF-HEALING REPAIR ---")
    print(f"Repair attempt: {current_attempt}/{max_retries}")
    print(f"Error type: {error_type}")
    print(f"Strategy: {recovery_strategy}")

    try:
        repair_result = repair_project_files(
            project_directory=project_directory,
            error_message=error_message,
            error_type=error_type,
            recovery_knowledge=recovery_knowledge,
            recovery_strategy=recovery_strategy,
            recovery_path=recovery_path,
        )

        return {
            "repair_result": repair_result,
            "repair_attempts": current_attempt,
            "message": "Gemini self-healing repair completed.",
            "history": _append_history(
                state,
                {
                    "type": "repair",
                    "attempt": current_attempt,
                    "error_type": error_type,
                    "recovery_strategy": recovery_strategy,
                    "recovery_path": recovery_path,
                    "message": "Gemini self-healing repair completed.",
                    "result": repair_result,
                },
            ),
        }

    except Exception as error:
        print(f"Self-healing error: {error}")

        repair_result = {
            "success": False,
            "error": str(error),
        }

        return {
            "repair_result": repair_result,
            "repair_attempts": current_attempt,
            "message": f"Self-healing failed: {error}",
            "history": _append_history(
                state,
                {
                    "type": "repair",
                    "attempt": current_attempt,
                    "error_type": error_type,
                    "recovery_strategy": recovery_strategy,
                    "recovery_path": recovery_path,
                    "message": f"Self-healing failed: {error}",
                    "result": repair_result,
                },
            ),
        }


# ---------------------------------------------------------
# 6. DECIDE WHETHER TO RETRY
# ---------------------------------------------------------

def should_retry(state: RecoveryState):
    """
    PASS → END.

    FAIL + retries remaining → classify the CURRENT error again.

    FAIL + retry limit reached → END.
    """

    validation_result = state.get(
        "validation_result",
        {},
    )

    if validation_result.get("success"):
        print("\n--- RECOVERY DECISION ---")
        print("Project passed validation. Ending workflow.")
        return "done"

    repair_attempts = state.get(
        "repair_attempts",
        0,
    )

    max_retries = state.get(
        "max_retries",
        3,
    )

    print("\n--- RECOVERY DECISION ---")
    print(
        f"Repair attempts: {repair_attempts}/{max_retries}"
    )

    if repair_attempts >= max_retries:
        print(
            "Maximum repair attempts reached. Ending workflow."
        )
        return "done"

    print(
        "Repair attempts remain. "
        "Classifying the CURRENT validation error."
    )

    return "repair"


# ---------------------------------------------------------
# 7. BUILD LANGGRAPH WORKFLOW
# ---------------------------------------------------------

def build_recovery_workflow():

    workflow = StateGraph(RecoveryState)

    workflow.add_node(
        "validate_project",
        validate_project_node,
    )

    workflow.add_node(
        "classify_error",
        classify_error_node,
    )

    workflow.add_node(
        "retrieve_knowledge",
        retrieve_knowledge_node,
    )

    workflow.add_node(
        "select_recovery_strategy",
        select_recovery_strategy_node,
    )

    workflow.add_node(
        "execute_repair",
        execute_repair_node,
    )

    workflow.add_edge(
        START,
        "validate_project",
    )

    workflow.add_conditional_edges(
        "validate_project",
        should_retry,
        {
            "done": END,
            "repair": "classify_error",
        },
    )

    workflow.add_edge(
        "classify_error",
        "retrieve_knowledge",
    )

    workflow.add_edge(
        "retrieve_knowledge",
        "select_recovery_strategy",
    )

    workflow.add_edge(
        "select_recovery_strategy",
        "execute_repair",
    )

    workflow.add_edge(
        "execute_repair",
        "validate_project",
    )

    return workflow.compile()


# ---------------------------------------------------------
# 8. RUN RECOVERY WORKFLOW
# ---------------------------------------------------------

def run_recovery_workflow(
    project_directory,
    max_retries=5,
):
    """
    Run the complete autonomous validation/recovery loop.
    """

    workflow = build_recovery_workflow()

    initial_state = {
        "project_directory": str(project_directory),
        "max_retries": max_retries,
        "repair_attempts": 0,
        "history": [],
        "success": False,
        "message": "Starting project validation.",
    }

    result = workflow.invoke(initial_state)

    # Make sure the final state always contains stable UI fields.
    result.setdefault(
        "history",
        [],
    )
    result.setdefault(
        "repair_attempts",
        0,
    )
    result.setdefault(
        "success",
        bool(
            result.get(
                "validation_result",
                {},
            ).get("success", False)
        ),
    )

    if result.get("success"):
        result["message"] = "Project validation passed."
    else:
        result.setdefault(
            "message",
            "Project validation failed.",
        )

    return result
