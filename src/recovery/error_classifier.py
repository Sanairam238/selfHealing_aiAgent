"""
Classifies runtime and validation errors into recovery categories.
"""

from src.rag.recovery_knowledge import retrieve_recovery_knowledge


def classify_error(error_message):
    """
    Classify an error using direct error patterns first,
    then fall back to the recovery knowledge base.
    """

    if not error_message:
        return {
            "error_type": "unknown_error",
            "confidence": 0,
            "reason": "No error message was provided.",
        }

    error_lower = error_message.lower()

    # ---------------------------------------------------------
    # SYNTAX ERRORS
    # ---------------------------------------------------------

    syntax_markers = [
        "syntaxerror",
        "invalid syntax",
        "expected ':'",
        "expected an indented block",
        "unexpected indent",
        "unexpected unindent",
        "unindent does not match",
        "unterminated string",
        "unterminated triple-quoted string",
        "was never closed",
    ]

    if any(marker in error_lower for marker in syntax_markers):
        return {
            "error_type": "syntax_error",
            "confidence": 1,
            "reason": (
                "The error message contains a Python syntax-error "
                "pattern."
            ),
        }

    # ---------------------------------------------------------
    # DEPENDENCY / IMPORT ERRORS
    # ---------------------------------------------------------

    dependency_markers = [
        "modulenotfounderror",
        "no module named",
        "importerror",
        "cannot import name",
    ]

    if any(marker in error_lower for marker in dependency_markers):
        return {
            "error_type": "dependency_error",
            "confidence": 1,
            "reason": (
                "The error message contains a missing or invalid "
                "Python import pattern."
            ),
        }

    # ---------------------------------------------------------
    # FILE / PATH ERRORS
    # ---------------------------------------------------------

    file_markers = [
        "filenotfounderror",
        "no such file or directory",
        "cannot find the path",
        "path does not exist",
    ]

    if any(marker in error_lower for marker in file_markers):
        return {
            "error_type": "file_error",
            "confidence": 1,
            "reason": (
                "The error message indicates that a required "
                "file or path could not be found."
            ),
        }

    # ---------------------------------------------------------
    # DATABASE ERRORS
    # ---------------------------------------------------------

    database_markers = [
        "sqlite3.operationalerror",
        "unable to open database file",
        "database is locked",
        "no such table",
        "sqlite",
    ]

    if any(marker in error_lower for marker in database_markers):
        return {
            "error_type": "database_error",
            "confidence": 1,
            "reason": (
                "The error message contains a database or SQLite "
                "failure pattern."
            ),
        }

    # ---------------------------------------------------------
    # PORT ERRORS
    # ---------------------------------------------------------

    port_markers = [
        "address already in use",
        "only one usage of each socket address",
        "port is already in use",
        "winerror 10048",
    ]

    if any(marker in error_lower for marker in port_markers):
        return {
            "error_type": "port_error",
            "confidence": 1,
            "reason": (
                "The error message indicates that the requested "
                "network port is already in use."
            ),
        }

    # ---------------------------------------------------------
    # CONFIGURATION ERRORS
    # ---------------------------------------------------------

    configuration_markers = [
        "configuration error",
        "missing configuration",
        "environment variable",
        "missing environment variable",
    ]

    if any(marker in error_lower for marker in configuration_markers):
        return {
            "error_type": "configuration_error",
            "confidence": 1,
            "reason": (
                "The error message appears to indicate a missing "
                "or invalid configuration."
            ),
        }

    # ---------------------------------------------------------
    # RUNTIME / APPLICATION CODE ERRORS
    # ---------------------------------------------------------
    #
    # These are important for errors such as:
    #
    # NameError:
    #     name 'date' is not defined
    #
    # AttributeError:
    #     object has no attribute ...
    #
    # TypeError:
    #     unsupported operand type ...
    #
    # These errors usually require Gemini to inspect the CURRENT
    # project source code and repair the actual cause.
    # ---------------------------------------------------------

    runtime_markers = [
        "nameerror:",
        "unboundlocalerror:",
        "attributeerror:",
        "typeerror:",
        "indexerror:",
        "keyerror:",
        "valueerror:",
        "zerodivisionerror:",
        "runtimeerror:",
        "assertionerror:",
        "recursionerror:",
        "overflowerror:",
    ]

    if any(marker in error_lower for marker in runtime_markers):
        return {
            "error_type": "runtime_error",
            "confidence": 1,
            "reason": (
                "The application reached runtime execution but "
                "encountered a Python application-code error."
            ),
        }

    # ---------------------------------------------------------
    # GENERIC TRACEBACK
    # ---------------------------------------------------------
    #
    # If Streamlit/application execution produced a traceback but
    # the exact exception type was not recognized above, classify
    # it as a runtime error rather than immediately calling it
    # unknown.
    # ---------------------------------------------------------

    if "traceback (most recent call last):" in error_lower:
        return {
            "error_type": "runtime_error",
            "confidence": 0.8,
            "reason": (
                "The application produced a runtime traceback "
                "during execution."
            ),
        }

    # ---------------------------------------------------------
    # FALL BACK TO RAG
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # UNKNOWN ERROR
    # ---------------------------------------------------------

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