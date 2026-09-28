import json
import os
import re
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv


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


def extract_json(text):
    """
    Safely extract JSON from Gemini's response.

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

    # Find the JSON object
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

    # First attempt: normal JSON parsing
    try:
        return json.loads(json_text)

    except json.JSONDecodeError:
        pass

    # Second attempt:
    # Repair invalid backslash escapes that commonly occur
    # when Gemini returns source code inside JSON strings.
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
        workspace /
        "invalid_gemini_response.txt"
    )

    response_file.write_text(
        text,
        encoding="utf-8",
    )


def _collect_project_files(project_directory):
    """
    Read all text-based project files while ignoring
    virtual environments and cache directories.
    """

    project_directory = Path(
        project_directory
    ).resolve()

    project_files = []

    ignored_directories = {
        ".venv",
        "__pycache__",
        ".git",
        "node_modules",
    }

    for file_path in project_directory.rglob("*"):

        if not file_path.is_file():
            continue

        if any(
            ignored in file_path.parts
            for ignored in ignored_directories
        ):
            continue

        try:

            relative_path = file_path.relative_to(
                project_directory
            )

            content = file_path.read_text(
                encoding="utf-8"
            )

            project_files.append(
                {
                    "path": str(relative_path),
                    "content": content,
                }
            )

        except (
            UnicodeDecodeError,
            OSError,
        ):
            continue

    return project_files


def _safe_target_path(
    project_directory,
    relative_path,
):
    """
    Make sure the AI cannot write files outside
    the generated project directory.
    """

    project_directory = Path(
        project_directory
    ).resolve()

    relative_path = Path(relative_path)

    # Reject absolute paths
    if relative_path.is_absolute():
        return None

    target_path = (
        project_directory /
        relative_path
    ).resolve()

    try:
        target_path.relative_to(
            project_directory
        )
    except ValueError:
        return None

    return target_path


def repair_project_files(
    project_directory,
    error_message,
):
    """
    Ask Gemini to analyze the generated project,
    identify the problem, repair the necessary files,
    and write the repaired files back to the project.
    """

    project_directory = Path(
        project_directory
    ).resolve()

    if not project_directory.exists():
        raise ValueError(
            f"Project directory does not exist: "
            f"{project_directory}"
        )

    project_files = _collect_project_files(
        project_directory
    )

    if not project_files:
        raise ValueError(
            "No project files were found to repair."
        )

    project_files_json = json.dumps(
        project_files,
        indent=2,
        ensure_ascii=False,
    )

    prompt = f"""
You are the self-healing software repair agent.

A generated software project was automatically executed
and failed during validation.

Your job is to:

1. Analyze the error.
2. Identify the file or files responsible.
3. Determine the root cause.
4. Repair the affected code.
5. Return the complete corrected contents of every file
   that needs to be changed.

ERROR FROM AUTOMATIC VALIDATION:
{error_message}

PROJECT DIRECTORY:
{project_directory}

CURRENT PROJECT FILES:
{project_files_json}

IMPORTANT RULES:

- Repair the existing project.
- Do not redesign the application.
- Do not change the application's intended functionality.
- Do not replace the project with an unrelated example.
- Only modify files that actually need repair.
- Return complete file contents for repaired files.
- Preserve the technology stack specified by the project.
- Do not invent unrelated features.
- Do not include Markdown.
- Do not include explanations outside the JSON object.

Return ONLY this JSON structure:

{{
    "explanation": "Short explanation of the detected problem and repair",
    "files": [
        {{
            "path": "relative/path/to/file",
            "content": "complete corrected file content"
        }}
    ]
}}

The "files" array must contain only files that need to be repaired.
"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    )

    repaired_result = extract_json(
        response.text
    )

    if not isinstance(
        repaired_result,
        dict,
    ):
        raise ValueError(
            "Gemini repair response is not a JSON object."
        )

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
        raise ValueError(
            "Gemini repair response contains "
            "an invalid files list."
        )

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
            continue

        target_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target_path.write_text(
            content,
            encoding="utf-8",
        )

        saved_files.append(
            str(
                target_path.relative_to(
                    project_directory
                )
            )
        )

    return {
        "explanation": explanation,
        "files": repaired_files,
        "saved_files": saved_files,
    }