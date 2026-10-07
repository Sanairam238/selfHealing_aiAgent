from src.recovery.recovery_workflow import (
    run_recovery_workflow,
)


def run_with_self_healing(
    project_directory,
    max_retries=3,
):
    """
    Run the autonomous recovery workflow.

    This function keeps the original interface expected by
    the Streamlit application while delegating the actual
    validation, classification, RAG, strategy selection,
    repair, and retry loop to recovery_workflow.py.
    """

    return run_recovery_workflow(
        project_directory=project_directory,
        max_retries=max_retries,
    )
