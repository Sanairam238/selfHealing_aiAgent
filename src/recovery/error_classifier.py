"""
Classifies runtime and validation errors into recovery categories.
"""

from src.rag.recovery_knowledge import retrieve_recovery_knowledge


def classify_error(error_message):
    """
    Classify an error using the recovery knowledge base.
    """

    if not error_message:
        return {
            "error_type": "unknown_error",
            "confidence": 0,
            "reason": "No error message was provided.",
        }

    retrieved_knowledge = retrieve_recovery_knowledge(
        error_message,
        top_k=1,
    )

    if retrieved_knowledge:

        best_match = retrieved_knowledge[0]

        return {
            "error_type": best_match["error_type"],
            "confidence": 1,
            "reason": (
                "The error matched a known recovery category "
                "using keyword-based retrieval."
            ),
        }

    return {
        "error_type": "unknown_error",
        "confidence": 0,
        "reason": (
            "No known recovery category matched the error."
        ),
    }


def get_error_type(error_message):
    """
    Return only the error category.
    """

    result = classify_error(error_message)

    return result["error_type"]