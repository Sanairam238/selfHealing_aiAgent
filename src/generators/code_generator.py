import json
import os
import re

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
# JSON PARSER
# =========================================================

def extract_json(text):
    """
    Extract a JSON object from Gemini's response.
    """

    if not text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    # Remove Markdown code fences if Gemini adds them.
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
    # Try normal JSON parsing first
    # -----------------------------------------------------

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        pass

    # -----------------------------------------------------
    # Find the JSON object
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
    # Try parsing the extracted object
    # -----------------------------------------------------

    try:
        return json.loads(json_text)

    except json.JSONDecodeError:
        pass

    # -----------------------------------------------------
    # Try repairing invalid backslash escapes
    # -----------------------------------------------------

    repaired_json = re.sub(
        r'\\(?!["\\/bfnrtu])',
        r"\\\\",
        json_text,
    )

    try:
        return json.loads(repaired_json)

    except json.JSONDecodeError as error:

        # Save the raw response for debugging.
        workspace = "workspace"

        os.makedirs(
            workspace,
            exist_ok=True,
        )

        response_file = os.path.join(
            workspace,
            "invalid_code_generation_response.txt",
        )

        with open(
            response_file,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(text)

        raise ValueError(
            "Gemini returned malformed JSON.\n"
            f"JSON error: {error}\n"
            f"Raw response saved to: {response_file}"
        )


# =========================================================
# PROJECT CODE GENERATION
# =========================================================

def generate_project_files(project_blueprint):
    """
    Generate complete source-code files dynamically
    from the approved project blueprint.
    """

    prompt = f"""
You are an expert software developer and
system architect.

Generate complete source-code files for the project
described in the approved project blueprint below.

APPROVED PROJECT BLUEPRINT:
{project_blueprint}

IMPORTANT RULES:

1. Generate the application dynamically from the
   approved blueprint.

2. Follow the project type, features, architecture,
   and technology stack specified in the blueprint.

3. Do not assume that the project is a Trip Planner.

4. Do not assume that the project is a Student
   Attendance Management System.

5. Do not force Flask, Streamlit, SQLite, React,
   Node.js, or any other technology.

6. Use the technologies explicitly specified in
   the approved blueprint.

7. If the blueprint does not specify a technology,
   choose a reasonable technology and document
   that choice in README.md.

8. Do not add unrelated features.

9. Do not use hard-coded application-specific
   names, routes, database tables, or models
   unless they are required by the blueprint.

10. Generate files that match the requested
    application.

11. Every generated file must contain complete
    runnable content.

12. Use relative file paths only.

13. Use forward slashes in file paths.

14. Never generate absolute file paths.

15. Never generate files outside the project.

16. Include validation and error handling where
    appropriate.

17. Include requirements.txt or the appropriate
    dependency file when required.

18. Include README.md with setup and execution
    instructions.

19. Do not require external API keys unless the
    blueprint explicitly requires an external service.

20. Do not generate placeholder code.

21. Do not use TODO implementations.

22. Generate complete source code.

23. Return ONLY valid JSON.

24. Do not return Markdown outside the JSON object.

25. All source-code content must be correctly
    encoded as JSON strings.

26. Correctly escape quotes, backslashes, and
    newline characters inside file contents.

27. Do not include explanations outside the JSON.

Return exactly this structure:

{{
    "files": [
        {{
            "path": "relative/path/to/file",
            "content": "complete file content"
        }}
    ]
}}
"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    )

    return extract_json(response.text)