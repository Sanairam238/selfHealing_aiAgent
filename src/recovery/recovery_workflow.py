"""
LangGraph-based self-healing recovery workflow.

Flow:

    Validate project
          ↓
      Error found
          ↓
    Classify error
          ↓
    Retrieve RAG knowledge
          ↓
    Select recovery strategy
          ↓
      Gemini repair
          ↓
    Validate project again
          ↓
       ┌───┴───┐
      PASS     FAIL
       ↓        ↓
      END   Check retry limit
                ↓
          ┌─────┴─────┐
       retries      limit
       remain       reached
          ↓             ↓
        repair         END
          ↓
       validate
"""

from typing import TypedDict

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
    """Shared state passed between LangGraph nodes."""

    project_directory: str

    error_message: str
    error_type: str
    confidence: int

    recovery_knowledge: str
    recovery_strategy: str
    recovery_path: list

    repair_result: dict
    validation_result: dict

    repair_attempts: int
    max_retries: int

    success: bool
    message: str


# ---------------------------------------------------------
# 1. VALIDATE PROJECT
# ---------------------------------------------------------

def validate_project_node(state: RecoveryState):
    """Run the generated project and capture any failure."""

    project_directory = state.get("project_directory")

    if not project_directory:
        return {
            "success": False,
            "message": "Project directory was not provided.",
        }

    print("\n--- PROJECT VALIDATION ---")

    validation_result = run_project_checks(project_directory)

    if validation_result["success"]:
        print("Project validation PASSED.")

        return {
            "validation_result": validation_result,
            "success": True,
            "message": "Project validation passed.",
        }

    print("Project validation FAILED.")

    return {
        "validation_result": validation_result,
        "error_message": validation_result.get(
            "summary",
            "Project validation failed.",
        ),
        "success": False,
        "message": "Project validation failed.",
    }


# ---------------------------------------------------------
# 2. CLASSIFY ERROR
# ---------------------------------------------------------

def classify_error_node(state: RecoveryState):
    """Classify the detected error."""

    error_message = state.get("error_message", "")

    print("\n--- ERROR CLASSIFICATION ---")

    classification = classify_error(error_message)

    print(
        f"Error type: {classification['error_type']}"
    )

    print(
        f"Confidence: {classification['confidence']}"
    )

    return {
        "error_type": classification["error_type"],
        "confidence": classification["confidence"],
        "message": classification["reason"],
    }


# ---------------------------------------------------------
# 3. RETRIEVE RECOVERY KNOWLEDGE
# ---------------------------------------------------------

def retrieve_knowledge_node(state: RecoveryState):
    """Retrieve relevant recovery knowledge using RAG."""

    error_message = state.get("error_message", "")

    print("\n--- RAG RECOVERY KNOWLEDGE ---")

    knowledge = format_recovery_context(
        error_message,
        top_k=3,
    )

    return {
        "recovery_knowledge": knowledge,
    }


# ---------------------------------------------------------
# 4. SELECT RECOVERY STRATEGY
# ---------------------------------------------------------

def select_recovery_strategy_node(state: RecoveryState):
    """Select a recovery strategy using the NetworkX graph."""

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
    }


# ---------------------------------------------------------
# 5. EXECUTE GEMINI REPAIR
# ---------------------------------------------------------

def execute_repair_node(state: RecoveryState):
    """Ask Gemini to repair the generated project."""

    project_directory = state.get("project_directory")

    error_message = state.get(
        "error_message",
        "",
    )

    if not project_directory:
        return {
            "success": False,
            "message": "Project directory was not provided.",
        }

    repair_attempts = state.get(
        "repair_attempts",
        0,
    )

    current_attempt = repair_attempts + 1

    print("\n--- SELF-HEALING REPAIR ---")
    print(
        f"Repair attempt: {current_attempt}/"
        f"{state.get('max_retries', 3)}"
    )

    try:

        repair_result = repair_project_files(
            project_directory=project_directory,
            error_message=error_message,
        )

        return {
            "repair_result": repair_result,
            "repair_attempts": current_attempt,
            "success": True,
            "message": "Gemini self-healing repair completed.",
        }

    except Exception as error:

        print(f"Self-healing error: {error}")

        return {
            "repair_attempts": current_attempt,
            "success": False,
            "message": f"Self-healing failed: {error}",
        }


# ---------------------------------------------------------
# 6. DECIDE WHETHER TO RETRY
# ---------------------------------------------------------

def should_retry(state: RecoveryState):
    """
    Decide what happens after project validation.

    PASS:
        END

    FAIL + retries remaining:
        Repair again

    FAIL + retry limit reached:
        END
    """

    validation_result = state.get(
        "validation_result",
        {},
    )

    # ---------------------------------------------
    # CASE 1: PROJECT PASSED
    # ---------------------------------------------

    if validation_result.get("success"):
        print("\n--- RECOVERY DECISION ---")
        print("Project passed validation. Ending workflow.")

        return "done"

    # ---------------------------------------------
    # CASE 2: PROJECT FAILED
    # ---------------------------------------------

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

    # ---------------------------------------------
    # RETRY LIMIT REACHED
    # ---------------------------------------------

    if repair_attempts >= max_retries:

        print(
            "Maximum repair attempts reached. "
            "Ending workflow."
        )

        return "done"

    # ---------------------------------------------
    # RETRIES REMAIN
    # ---------------------------------------------

    print("Repair attempts remain. Starting repair.")

    return "repair"


# ---------------------------------------------------------
# 7. BUILD LANGGRAPH WORKFLOW
# ---------------------------------------------------------

def build_recovery_workflow():

    workflow = StateGraph(RecoveryState)

    # ---------------------------------------------
    # NODES
    # ---------------------------------------------

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

    # ---------------------------------------------
    # START → VALIDATE
    # ---------------------------------------------

    workflow.add_edge(
        START,
        "validate_project",
    )

    # ---------------------------------------------
    # VALIDATE → DECISION
    #
    # IMPORTANT:
    # This now uses should_retry().
    #
    # The previous version always sent every
    # failed validation directly to repair.
    # ---------------------------------------------

    workflow.add_conditional_edges(
        "validate_project",
        should_retry,
        {
            "done": END,
            "repair": "classify_error",
        },
    )

    # ---------------------------------------------
    # ERROR CLASSIFICATION
    # ---------------------------------------------

    workflow.add_edge(
        "classify_error",
        "retrieve_knowledge",
    )

    # ---------------------------------------------
    # RAG
    # ---------------------------------------------

    workflow.add_edge(
        "retrieve_knowledge",
        "select_recovery_strategy",
    )

    # ---------------------------------------------
    # STRATEGY
    # ---------------------------------------------

    workflow.add_edge(
        "select_recovery_strategy",
        "execute_repair",
    )

    # ---------------------------------------------
    # REPAIR → VALIDATE
    # ---------------------------------------------

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
    max_retries=3,
):
    """
    Run the complete self-healing workflow.

    The workflow repeatedly:

        validate
          ↓
        classify
          ↓
        retrieve knowledge
          ↓
        select strategy
          ↓
        repair
          ↓
        validate again

    until:

        1. The project passes validation

        OR

        2. The maximum number of repair attempts
           has been reached.
    """

    workflow = build_recovery_workflow()

    initial_state = {
        "project_directory": project_directory,
        "max_retries": max_retries,
        "repair_attempts": 0,
    }

    result = workflow.invoke(
        initial_state
    )

    return result