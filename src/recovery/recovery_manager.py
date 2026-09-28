from src.execution.project_runner import (
    run_project_checks,
)

from src.recovery.self_healer import (
    repair_project_files,
)


def run_with_self_healing(
    project_directory,
    max_retries=3,
):
    """
    Run checks and automatically repair failures.
    """

    history = []

    for attempt in range(max_retries + 1):

        check_result = run_project_checks(
            project_directory
        )

        history.append(
            {
                "attempt": attempt + 1,
                "type": "validation",
                "result": check_result,
            }
        )

        if check_result["success"]:

            return {
                "success": True,
                "attempts": attempt + 1,
                "history": history,
                "message": (
                    "The project passed all automatic checks."
                ),
            }

        if attempt == max_retries:

            return {
                "success": False,
                "attempts": attempt + 1,
                "history": history,
                "message": (
                    "The project still has errors after "
                    f"{max_retries} repair attempts."
                ),
            }

        repair_result = repair_project_files(
            project_directory=project_directory,
            error_message=check_result["summary"],
        )

        history.append(
            {
                "attempt": attempt + 1,
                "type": "repair",
                "result": repair_result,
            }
        )

    return {
        "success": False,
        "attempts": max_retries + 1,
        "history": history,
        "message": "Recovery process ended.",
    }