import json
import os
import re
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY was not found in the .env file."
    )

genai.configure(api_key=api_key)

model = genai.GenerativeModel(
    "gemini-3.5-flash-lite"
)


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text):
    """
    Safely extract a JSON object from Gemini's response.

    Handles:
    - Markdown code fences
    - Extra text around JSON
    - Invalid backslash escapes
    """

    if not text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    # Remove Markdown code fences
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^```\s*",
        "",
        text,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    text = text.strip()

    start_index = text.find("{")
    end_index = text.rfind("}")

    if start_index == -1 or end_index == -1:

        _save_invalid_response(text)

        raise ValueError(
            "Gemini did not return a valid JSON object."
        )

    json_text = text[
        start_index:end_index + 1
    ]

    # First attempt
    try:

        return json.loads(json_text)

    except json.JSONDecodeError:
        pass

    # Second attempt:
    # repair invalid backslash escapes
    repaired_json = re.sub(
        r'\\(?!["\\/bfnrtu])',
        r"\\\\",
        json_text,
    )

    try:

        return json.loads(repaired_json)

    except json.JSONDecodeError as error:

        _save_invalid_response(text)

        raise ValueError(
            "Gemini returned malformed JSON. "
            "The response was saved to "
            "workspace/invalid_gemini_response.txt. "
            f"Details: {error}"
        )


# ============================================================
# SAVE INVALID GEMINI RESPONSE
# ============================================================

def _save_invalid_response(text):
    """
    Save Gemini's invalid response for debugging.
    """

    workspace = Path("workspace")

    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    response_file = (
        workspace
        / "invalid_gemini_response.txt"
    )

    response_file.write_text(
        text,
        encoding="utf-8",
    )


# ============================================================
# COLLECT PROJECT FILES
# ============================================================

def _collect_project_files(project_directory):
    """
    Collect text-based project files recursively.

    Excludes virtual environments, caches, Git metadata,
    and dependency folders.
    """

    project_directory = Path(
        project_directory
    )

    excluded_directories = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
    }

    text_extensions = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".json",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".html",
        ".css",
        ".sql",
    }

    files = []

    for path in project_directory.rglob("*"):

        if not path.is_file():
            continue

        if any(
            part in excluded_directories
            for part in path.parts
        ):
            continue

        if path.suffix.lower() not in text_extensions:
            continue

        try:

            content = path.read_text(
                encoding="utf-8"
            )

            relative_path = path.relative_to(
                project_directory
            )

            files.append({
                "path": str(relative_path),
                "content": content,
            })

        except (
            UnicodeDecodeError,
            OSError,
        ):
            continue

    return files


# ============================================================
# SAFE FILE PATH
# ============================================================

def _safe_target_path(
    project_directory,
    relative_path,
):
    """
    Prevent Gemini from writing outside the project directory.
    """

    project_directory = Path(
        project_directory
    ).resolve()

    relative_path = Path(
        relative_path
    )

    # Reject absolute paths
    if relative_path.is_absolute():
        return None

    target_path = (
        project_directory
        / relative_path
    ).resolve()

    try:

        target_path.relative_to(
            project_directory
        )

    except ValueError:

        return None

    return target_path


# ============================================================
# GEMINI ERROR HANDLING
# ============================================================

def _get_gemini_error_message(error):
    """
    Convert Gemini/API errors into a readable message.
    """

    error_text = str(error)

    if (
        "429" in error_text
        or "ResourceExhausted" in error_text
    ):

        return (
            "Gemini API quota or rate limit was reached."
        )

    if (
        "500" in error_text
        or "502" in error_text
        or "503" in error_text
        or "504" in error_text
        or "ServiceUnavailable" in error_text
        or "Deadline" in error_text
        or "deadline" in error_text
    ):

        return (
            "Gemini service temporarily failed "
            f"({error_text})"
        )

    if (
        "401" in error_text
        or "403" in error_text
        or "Unauthenticated" in error_text
        or "PermissionDenied" in error_text
    ):

        return (
            "Gemini API authentication or permission "
            "failed. Check GEMINI_API_KEY."
        )

    return (
        "Gemini repair request failed: "
        f"{error_text}"
    )


# ============================================================
# SELF-HEALING REPAIR
# ============================================================

def repair_project_files(
    project_directory,
    error_message,
    error_type="unknown_error",
    recovery_knowledge="",
    recovery_strategy="analyze_with_gemini",
    recovery_path=None,
):
    """
    Ask Gemini to analyze the CURRENT project state,
    identify the root cause of the CURRENT validation error,
    repair only the necessary files, and save them.
    """

    project_directory = Path(
        project_directory
    ).resolve()

    if not project_directory.exists():

        raise ValueError(
            "Project directory does not exist: "
            f"{project_directory}"
        )

    # --------------------------------------------------------
    # COLLECT CURRENT PROJECT STATE
    # --------------------------------------------------------

    project_files = _collect_project_files(
        project_directory
    )

    if not project_files:

        raise ValueError(
            "No project files were found to repair."
        )

    if recovery_path is None:
        recovery_path = []

    project_files_json = json.dumps(
        project_files,
        indent=2,
        ensure_ascii=False,
    )

    recovery_path_text = " → ".join(
        recovery_path
    )

    # ========================================================
    # GEMINI REPAIR PROMPT
    # ========================================================

    prompt = f"""
You are the self-healing software repair agent.

A software project was automatically validated by a
project runner.

The CURRENT project state produced the validation error
shown below.

Your responsibility is to diagnose the CURRENT error,
inspect the CURRENT project files, identify the actual
root cause, make the smallest safe repair, and return
the complete contents of the files that must change.

============================================================
CURRENT VALIDATION ERROR
============================================================

{error_message}

============================================================
ERROR CLASSIFICATION
============================================================

{error_type}

============================================================
RECOVERY STRATEGY
============================================================

{recovery_strategy}

============================================================
RECOVERY PATH
============================================================

{recovery_path_text}

============================================================
RECOVERY KNOWLEDGE FROM RAG
============================================================

{recovery_knowledge}

============================================================
CURRENT PROJECT FILES
============================================================

{project_files_json}

============================================================
CORE REPAIR RULES
============================================================

1. The validation error above is the PRIMARY source of truth.

2. Inspect the CURRENT project files before making any change.

3. Diagnose the actual root cause.

4. Repair the root cause, not merely the visible symptom.

5. Preserve the existing application's intended functionality.

6. Preserve the existing technology stack.

7. Do not redesign the application.

8. Do not replace the project with a new example project.

9. Do not add unrelated features.

10. Do not make unnecessary changes.

11. Prefer the smallest safe repair.

12. Only return files that actually need modification.

13. Return COMPLETE file contents for every modified file.

14. Do not delete files.

15. Do not perform destructive filesystem operations.

16. Do not modify working code unless required by the
    current validation error.

17. Do not assume that a previous repair was correct.

18. If this is a retry, treat the CURRENT validation error
    and CURRENT project files as authoritative.

============================================================
RUNTIME ERROR REPAIR
============================================================

When ERROR CLASSIFICATION is:

runtime_error

you MUST inspect the traceback and identify the actual
source-code cause.

Pay particular attention to errors such as:

NameError
UnboundLocalError
AttributeError
TypeError
ValueError
KeyError
IndexError
ZeroDivisionError
RuntimeError
AssertionError

For a NameError:

- Locate the exact undefined variable or name.
- Find where that name is used.
- Inspect the imports and surrounding code.
- Determine whether the correct repair is a missing import,
  incorrect variable name, missing definition, or another
  structural issue.
- Make the smallest correct repair.

Example:

If the current application contains:

    value=date.today()

and the traceback says:

    NameError: name 'date' is not defined

inspect the imports.

If the intended code clearly uses Python's datetime date
class and it is missing, the appropriate repair may be:

    from datetime import date

Do NOT blindly add imports.

Verify that the imported symbol matches how the application
actually uses it.

For AttributeError:

- Inspect the object involved.
- Determine why the requested attribute does not exist.
- Repair the actual object/attribute mismatch.

For TypeError:

- Inspect the values and function signatures involved.
- Determine the incompatible types or arguments.
- Repair the underlying mismatch.

For KeyError:

- Inspect how the dictionary/key is created and consumed.
- Do not simply suppress the error.
- Repair the incorrect key access or data structure mismatch.

For IndexError:

- Inspect the collection and index assumptions.
- Repair the actual bounds or data-shape issue.

============================================================
SYNTAX ERROR REPAIR
============================================================

When ERROR CLASSIFICATION is:

syntax_error

treat the problem as a structural code problem.

Inspect the surrounding lines before repairing.

Preserve indentation.

Check:

- brackets
- parentheses
- strings
- indentation
- colons
- function definitions
- control structures
- imports

Do not introduce a second syntax error.

If a malformed control statement was accidentally inserted
and clearly does not represent intended application logic,
remove the malformed statement instead of wrapping working
application code inside it.

============================================================
DEPENDENCY ERROR REPAIR
============================================================

When ERROR CLASSIFICATION is:

dependency_error

inspect the failing import.

Determine whether:

- the import is invalid
- the module name is incorrect
- the import path is incorrect
- the project contains a local module with a wrong import
- a dependency is genuinely required

Do not invent packages unnecessarily.

============================================================
DATABASE ERROR REPAIR
============================================================

When ERROR CLASSIFICATION is:

database_error

inspect the database connection code.

Check:

- database path
- parent directory creation
- SQLite configuration
- connection initialization
- relative versus absolute paths

Preserve the existing database design.

============================================================
RETRY-AWARE BEHAVIOR
============================================================

This may be recovery cycle 1, 2, 3, or a later retry.

A previous repair may have:

- completely fixed the previous error
- partially fixed it
- exposed a second error
- introduced a new error

Therefore:

DO NOT repeat a previous repair simply because the recovery
strategy is the same.

Always diagnose the CURRENT error from the CURRENT project.

The current traceback has priority over assumptions about
earlier recovery cycles.

============================================================
FINAL VERIFICATION BEFORE RESPONSE
============================================================

Before returning the repaired files:

1. Re-read the affected files.

2. Verify that the current validation error is addressed.

3. Check that the repair does not introduce an obvious
   syntax error.

4. Check imports and variable definitions.

5. Check indentation and code structure.

6. Preserve existing application behavior.

7. Return only files that genuinely require changes.

============================================================
RESPONSE FORMAT
============================================================

Return ONLY valid JSON.

Do not use Markdown.

Do not wrap the response in ```json fences.

Use exactly this structure:

{{
    "explanation": "Short explanation of the root cause and repair",
    "files": [
        {{
            "path": "relative/path/to/file",
            "content": "complete corrected file content"
        }}
    ]
}}

The files array must contain ONLY files that need repair.

============================================================
END OF TASK
============================================================
"""

    # ========================================================
    # GEMINI API CALL
    # ========================================================

    try:

        print(
            "Sending CURRENT project state and "
            "validation error to Gemini..."
        )

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
            request_options={
                "timeout": 120,
            },
        )

    except Exception as error:

        readable_error = (
            _get_gemini_error_message(error)
        )

        print(
            f"Gemini repair failed: "
            f"{readable_error}"
        )

        return {
            "success": False,
            "explanation": readable_error,
            "files": [],
            "saved_files": [],
            "error": readable_error,
        }

    # ========================================================
    # PARSE GEMINI RESPONSE
    # ========================================================

    try:

        repaired_result = extract_json(
            response.text
        )

    except Exception as error:

        readable_error = str(error)

        print(
            "Gemini response parsing failed: "
            f"{readable_error}"
        )

        return {
            "success": False,
            "explanation": readable_error,
            "files": [],
            "saved_files": [],
            "error": readable_error,
        }

    # ========================================================
    # VALIDATE RESPONSE OBJECT
    # ========================================================

    if not isinstance(
        repaired_result,
        dict,
    ):

        return {
            "success": False,
            "explanation": (
                "Gemini repair response is not "
                "a JSON object."
            ),
            "files": [],
            "saved_files": [],
            "error": (
                "Invalid Gemini repair response."
            ),
        }

    explanation = repaired_result.get(
        "explanation",
        "The AI repaired the project.",
    )

    repaired_files = repaired_result.get(
        "files",
        [],
    )

    if not isinstance(
        repaired_files,
        list,
    ):

        return {
            "success": False,
            "explanation": (
                "Gemini repair response contains "
                "an invalid files list."
            ),
            "files": [],
            "saved_files": [],
            "error": (
                "Invalid files list returned by Gemini."
            ),
        }

    # ========================================================
    # SAVE REPAIRED FILES
    # ========================================================

    saved_files = []

    for file in repaired_files:

        if not isinstance(
            file,
            dict,
        ):
            continue

        relative_path = file.get(
            "path"
        )

        content = file.get(
            "content"
        )

        if not relative_path:
            continue

        if content is None:
            continue

        target_path = _safe_target_path(
            project_directory,
            relative_path,
        )

        if target_path is None:

            print(
                "Rejected unsafe repair path: "
                f"{relative_path}"
            )

            continue

        target_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target_path.write_text(
            content,
            encoding="utf-8",
        )

        saved_relative_path = str(
            target_path.relative_to(
                project_directory
            )
        )

        saved_files.append(
            saved_relative_path
        )

        print(
            "Repaired file saved: "
            f"{saved_relative_path}"
        )

    # ========================================================
    # ENSURE A REAL REPAIR WAS RETURNED
    # ========================================================

    if not saved_files:

        return {
            "success": False,
            "explanation": (
                "Gemini did not provide any "
                "valid files to repair."
            ),
            "files": repaired_files,
            "saved_files": [],
            "error": (
                "No repair files were saved."
            ),
        }

    print(
        "Self-healing repair completed successfully."
    )

    return {
        "success": True,
        "explanation": explanation,
        "files": repaired_files,
        "saved_files": saved_files,
        "error": None,
    }