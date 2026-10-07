import json
import os
import re
import time

import google.generativeai as genai
from dotenv import load_dotenv


# =========================================================
# GEMINI SETUP
# =========================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY is missing from the .env file"
    )

genai.configure(api_key=api_key)

model = genai.GenerativeModel(
    "gemini-3.5-flash-lite"
)


# =========================================================
# CONSTANTS
# =========================================================

MAX_GENERATION_ATTEMPTS = 3


# =========================================================
# SAVE RAW RESPONSE
# =========================================================

def save_invalid_response(text, attempt):
    """
    Save Gemini's raw response when JSON parsing fails.
    """

    workspace = "workspace"

    os.makedirs(
        workspace,
        exist_ok=True,
    )

    response_file = os.path.join(
        workspace,
        f"invalid_code_generation_response_attempt_{attempt}.txt",
    )

    with open(
        response_file,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(text or "")

    return response_file


# =========================================================
# JSON PARSER
# =========================================================

def extract_json(text, attempt=1):
    """
    Extract and validate the JSON object returned by Gemini.

    Handles:
    - Markdown code fences
    - Extra text before/after JSON
    - Invalid backslash escapes
    """

    if not text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    # -----------------------------------------------------
    # Remove Markdown fences
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Normal JSON
    # -----------------------------------------------------

    try:
        data = json.loads(text)

        validate_generated_structure(data)

        return data

    except json.JSONDecodeError:
        pass

    # -----------------------------------------------------
    # Locate JSON object inside response
    # -----------------------------------------------------

    start_index = text.find("{")
    end_index = text.rfind("}")

    if start_index == -1 or end_index == -1:
        raise ValueError(
            "Gemini response does not contain a JSON object."
        )

    json_text = text[
        start_index:end_index + 1
    ]

    # -----------------------------------------------------
    # Try extracted JSON
    # -----------------------------------------------------

    try:
        data = json.loads(json_text)

        validate_generated_structure(data)

        return data

    except json.JSONDecodeError:
        pass

    # -----------------------------------------------------
    # Repair invalid backslash escapes
    # -----------------------------------------------------

    repaired_json = re.sub(
        r'\\(?!["\\/bfnrtu])',
        r"\\\\",
        json_text,
    )

    try:
        data = json.loads(repaired_json)

        validate_generated_structure(data)

        return data

    except json.JSONDecodeError as error:

        response_file = save_invalid_response(
            text,
            attempt,
        )

        raise ValueError(
            "Gemini returned malformed JSON.\n"
            f"JSON error: {error}\n"
            f"Raw response saved to: {response_file}"
        ) from error


# =========================================================
# GENERATED PROJECT VALIDATION
# =========================================================

def validate_generated_structure(data):
    """
    Ensure Gemini returned the structure expected by
    the project generator.
    """

    if not isinstance(data, dict):
        raise ValueError(
            "Gemini response must be a JSON object."
        )

    if "files" not in data:
        raise ValueError(
            'Gemini response is missing the "files" field.'
        )

    files = data["files"]

    if not isinstance(files, list):
        raise ValueError(
            '"files" must be a JSON array.'
        )

    if len(files) == 0:
        raise ValueError(
            "Gemini returned an empty project."
        )

    for index, file_data in enumerate(files):

        if not isinstance(file_data, dict):
            raise ValueError(
                f"File entry {index} is not an object."
            )

        if "path" not in file_data:
            raise ValueError(
                f"File entry {index} is missing its path."
            )

        if "content" not in file_data:
            raise ValueError(
                f"File entry {index} is missing its content."
            )

        path = file_data["path"]
        content = file_data["content"]

        if not isinstance(path, str):
            raise ValueError(
                f"File path at index {index} must be a string."
            )

        if not isinstance(content, str):
            raise ValueError(
                f"File content at index {index} must be a string."
            )

        # -------------------------------------------------
        # Security validation
        # -------------------------------------------------

        normalized_path = path.replace("\\", "/")

        if normalized_path.startswith("/"):
            raise ValueError(
                f"Absolute path detected: {path}"
            )

        if re.match(
            r"^[A-Za-z]:",
            normalized_path,
        ):
            raise ValueError(
                f"Windows absolute path detected: {path}"
            )

        if ".." in normalized_path.split("/"):
            raise ValueError(
                f"Path traversal detected: {path}"
            )

        if not normalized_path.strip():
            raise ValueError(
                f"Empty file path at index {index}."
            )


# =========================================================
# GENERATION PROMPT
# =========================================================

def build_generation_prompt(project_blueprint):
    """
    Build the Gemini code-generation prompt.
    """

    return f"""
You are an expert software developer and system architect.

Generate a complete runnable software project from the
APPROVED PROJECT BLUEPRINT below.

=========================================================
APPROVED PROJECT BLUEPRINT
=========================================================

{project_blueprint}

=========================================================
IMPORTANT GENERATION RULES
=========================================================

1. Generate the application dynamically from the blueprint.

2. Follow the project type, features, architecture and
   technology stack specified in the blueprint.

3. Do NOT assume the project is a Trip Planner.

4. Do NOT assume the project is a Student Attendance
   Management System.

5. Do NOT force Flask, Streamlit, SQLite, React, Node.js,
   Next.js or any other technology.

6. Use the technologies explicitly specified in the blueprint.

7. If the blueprint does not specify a technology,
   choose a reasonable technology and document that
   choice in README.md.

8. Do not add unrelated features.

9. Do not invent unnecessary application-specific routes,
   tables, models or services.

10. Every generated file must contain complete runnable
    content.

11. Do not generate placeholder implementations.

12. Do not use TODO implementations.

13. Include appropriate dependency files.

14. Include README.md with setup and execution instructions.

15. Do not require external API keys unless explicitly
    required by the blueprint.

16. Use relative file paths only.

17. Use forward slashes in file paths.

18. Never generate absolute paths.

19. Never generate files outside the project.

20. Include appropriate validation and error handling.

=========================================================
CRITICAL JSON REQUIREMENTS
=========================================================

Your ENTIRE response must be exactly ONE valid JSON object.

Do not write any explanation before the JSON.

Do not write any explanation after the JSON.

Do not use Markdown code fences.

Return exactly:

{{
  "files": [
    {{
      "path": "relative/path/to/file",
      "content": "complete file content"
    }}
  ]
}}

IMPORTANT:

- Every file must be represented as a JSON object.
- "path" must be a JSON string.
- "content" must be a JSON string.
- Escape every double quote inside source code.
- Escape every backslash that is part of source code.
- Represent line breaks correctly as JSON string escapes.
- Do not place raw unescaped newlines inside JSON strings.
- Do not truncate file contents.
- Do not omit source code.
- Do not return comments describing code instead of code.
- Do not return partial files.

Before responding, mentally verify that your complete response
is valid JSON and can be parsed by Python json.loads().
"""


# =========================================================
# SINGLE GENERATION ATTEMPT
# =========================================================

def _generate_once(prompt, attempt):
    """
    Perform one Gemini generation attempt.
    """

    try:

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
            request_options={
                "timeout": 180,
            },
        )

    except Exception as error:

        raise RuntimeError(
            "Gemini code generation failed or timed out.\n"
            f"Error: {error}"
        ) from error

    if not response:
        raise RuntimeError(
            "Gemini returned no response during code generation."
        )

    response_text = getattr(
        response,
        "text",
        None,
    )

    if not response_text:
        raise RuntimeError(
            "Gemini returned an empty response during "
            "code generation."
        )

    return extract_json(
        response_text,
        attempt=attempt,
    )


# =========================================================
# PROJECT CODE GENERATION
# =========================================================

def generate_project_files(project_blueprint):
    """
    Generate complete source-code files dynamically
    from the approved project blueprint.

    Gemini gets multiple chances if it returns malformed JSON.
    """

    prompt = build_generation_prompt(
        project_blueprint
    )

    last_error = None

    for attempt in range(
        1,
        MAX_GENERATION_ATTEMPTS + 1,
    ):

        try:

            result = _generate_once(
                prompt,
                attempt,
            )

            # -------------------------------------------------
            # Final structural validation
            # -------------------------------------------------

            validate_generated_structure(
                result
            )

            return result

        except ValueError as error:

            last_error = error

            # -------------------------------------------------
            # Tell Gemini why the previous response failed.
            # The next attempt gets a stricter instruction.
            # -------------------------------------------------

            prompt = build_generation_prompt(
                project_blueprint
            ) + f"""

=========================================================
PREVIOUS GENERATION ATTEMPT FAILED
=========================================================

Attempt: {attempt}

The previous response could not be parsed as valid JSON.

Error:
{error}

Generate the COMPLETE project again.

This time pay special attention to JSON escaping.

DO NOT output Markdown.

DO NOT output explanations.

DO NOT truncate the response.

The response must be directly compatible with:

json.loads(response_text)

=========================================================
"""

            if attempt < MAX_GENERATION_ATTEMPTS:
                time.sleep(1)

        except RuntimeError:
            raise

    # ---------------------------------------------------------
    # All attempts failed
    # ---------------------------------------------------------

    raise RuntimeError(
        "Source-code generation failed after "
        f"{MAX_GENERATION_ATTEMPTS} attempts.\n"
        f"Last error: {last_error}"
    ) from last_error