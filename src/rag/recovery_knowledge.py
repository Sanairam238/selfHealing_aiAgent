"""
Knowledge base for the self-healing and recovery system.

This module stores common software errors and possible recovery strategies.
The recovery workflow can retrieve relevant knowledge before asking Gemini
to generate a repair.
"""

RECOVERY_KNOWLEDGE = [
    {
        "error_type": "database_error",
        "keywords": [
            "sqlite3.operationalerror",
            "unable to open database file",
            "database",
            "sqlite",
            "db.create_all",
        ],
        "cause": (
            "The database file cannot be created or accessed. "
            "A parent directory may not exist or the application "
            "may be using an invalid database path."
        ),
        "solution": (
            "Check the database path and ensure its parent directory "
            "exists before creating or opening the database."
        ),
        "example_fix": (
            "Create the required data directory before initializing "
            "the database and use a valid project-relative database path."
        ),
    },
    {
        "error_type": "dependency_error",
        "keywords": [
            "modulenotfounderror",
            "no module named",
            "importerror",
            "cannot import",
        ],
        "cause": (
            "A required Python package is missing or the imported "
            "module name is incorrect."
        ),
        "solution": (
            "Identify the missing package, add it to requirements.txt "
            "if appropriate, and install the project's dependencies."
        ),
        "example_fix": (
            "Add the required dependency to requirements.txt and "
            "run pip install -r requirements.txt."
        ),
    },
    {
        "error_type": "syntax_error",
        "keywords": [
            "syntaxerror",
            "indentationerror",
            "unexpected indent",
            "invalid syntax",
        ],
        "cause": (
            "The generated source code contains invalid Python syntax "
            "or incorrect indentation."
        ),
        "solution": (
            "Inspect the reported file and line number and correct "
            "the syntax or indentation."
        ),
        "example_fix": (
            "Repair the affected source file while preserving "
            "the intended application functionality."
        ),
    },
    {
        "error_type": "file_error",
        "keywords": [
            "filenotfounderror",
            "no such file or directory",
            "file not found",
        ],
        "cause": (
            "The application is trying to access a file or directory "
            "that does not exist."
        ),
        "solution": (
            "Check the path, create required directories, and use "
            "project-relative paths where appropriate."
        ),
        "example_fix": (
            "Create the required directory before accessing the file "
            "or correct the incorrect project-relative path."
        ),
    },
    {
        "error_type": "port_error",
        "keywords": [
            "address already in use",
            "only one usage of each socket address",
            "port",
            "winerror 10048",
        ],
        "cause": (
            "The requested network port is already being used "
            "by another process."
        ),
        "solution": (
            "Identify the conflicting process or configure the "
            "application to use an available port."
        ),
        "example_fix": (
            "Use an available port without changing the application's "
            "intended functionality."
        ),
    },
    {
        "error_type": "configuration_error",
        "keywords": [
            "keyerror",
            "environment variable",
            "missing configuration",
            "config",
            "api key",
        ],
        "cause": (
            "The application expects configuration or environment "
            "variables that are missing or incorrectly configured."
        ),
        "solution": (
            "Identify the missing configuration and provide a safe "
            "project-specific default or documented environment variable."
        ),
        "example_fix": (
            "Add the required configuration handling and update "
            "the README with setup instructions when appropriate."
        ),
    },
]


def retrieve_recovery_knowledge(error_message, top_k=3):
    """
    Retrieve the most relevant recovery knowledge for an error.

    This is a lightweight keyword-based RAG prototype.
    """

    if not error_message:
        return []

    error_text = error_message.lower()

    scored_results = []

    for item in RECOVERY_KNOWLEDGE:

        score = 0

        for keyword in item["keywords"]:

            if keyword.lower() in error_text:
                score += 1

        if score > 0:

            scored_results.append(
                {
                    "score": score,
                    "knowledge": item,
                }
            )

    scored_results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return [
        item["knowledge"]
        for item in scored_results[:top_k]
    ]


def format_recovery_context(error_message, top_k=3):
    """
    Convert retrieved recovery knowledge into context
    that can be provided to the AI repair agent.
    """

    results = retrieve_recovery_knowledge(
        error_message,
        top_k=top_k,
    )

    if not results:
        return (
            "No matching recovery knowledge was found. "
            "Analyze the error using the project files and "
            "runtime information."
        )

    context_parts = []

    for index, item in enumerate(results, start=1):

        context_parts.append(
            f"""
Recovery Knowledge {index}
--------------------------
Error Type:
{item["error_type"]}

Likely Cause:
{item["cause"]}

Recommended Solution:
{item["solution"]}

Example Recovery:
{item["example_fix"]}
""".strip()
        )

    return "\n\n".join(context_parts)