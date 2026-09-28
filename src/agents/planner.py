import os
import json
import re

from dotenv import load_dotenv
import google.generativeai as genai


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY was not found in the .env file."
    )

genai.configure(api_key=api_key)


# Use the lower-quota model
model = genai.GenerativeModel(
    "gemini-3.5-flash-lite"
)


# --------------------------------------------------
# Extract JSON safely
# --------------------------------------------------

def extract_json(text):
    """
    Extract and parse a JSON object from Gemini's response.
    """

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

    # Locate the JSON object
    start_index = text.find("{")
    end_index = text.rfind("}")

    if start_index == -1 or end_index == -1:
        raise ValueError(
            "Gemini did not return a JSON object."
        )

    json_text = text[
        start_index:end_index + 1
    ]

    try:
        return json.loads(json_text)

    except json.JSONDecodeError:

        # Try to repair invalid backslashes
        repaired_json = re.sub(
            r'\\(?!["\\/bfnrtu])',
            r"\\\\",
            json_text,
        )

        try:
            return json.loads(repaired_json)

        except json.JSONDecodeError as error:

            # Save the response for debugging
            os.makedirs(
                "workspace",
                exist_ok=True,
            )

            with open(
                "workspace/invalid_planner_response.txt",
                "w",
                encoding="utf-8",
            ) as file:
                file.write(text)

            raise ValueError(
                "Gemini returned malformed JSON. "
                "The response was saved to "
                "workspace/invalid_planner_response.txt. "
                f"Details: {error}"
            )


# --------------------------------------------------
# Generate project plan
# --------------------------------------------------

def generate_project_plan(
    project_name,
    project_description,
):

    prompt = f"""
You are a software project planning assistant.

Project name:
{project_name}

Project description:
{project_description}

Create a clear implementation plan for this project.

Return ONLY valid JSON using exactly this structure:

{{
  "summary": [
    "Short step 1",
    "Short step 2",
    "Short step 3"
  ],
  "detailed_plan": "Detailed explanation of the architecture, features, database, backend, frontend, testing, and deployment."
}}

Important rules:

1. Return only one JSON object.
2. Do not use Markdown code fences.
3. Do not include backslashes unless they are valid JSON escapes.
4. Do not include source code in the plan.
5. Do not include unescaped double quotes inside text.
6. Keep the detailed plan as normal plain text.
7. Do not return comments outside the JSON object.
"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )

    return extract_json(
        response.text
    )


# --------------------------------------------------
# Modify project plan
# --------------------------------------------------

def modify_project_plan(
    current_plan,
    modification,
):

    if isinstance(current_plan, dict):

        current_plan_text = json.dumps(
            current_plan,
            ensure_ascii=False,
        )

    else:

        current_plan_text = str(
            current_plan
        )

    prompt = f"""
You are a software project planning assistant.

Current project plan:
{current_plan_text}

User's requested modification:
{modification}

Update the project plan according to the user's request.

Return ONLY valid JSON using exactly this structure:

{{
  "summary": [
    "Short step 1",
    "Short step 2",
    "Short step 3"
  ],
  "detailed_plan": "Updated detailed implementation plan."
}}

Important rules:

1. Return only one JSON object.
2. Do not use Markdown code fences.
3. Do not include source code.
4. Do not include unescaped double quotes inside text.
5. Do not include invalid backslash escapes.
6. Return no comments outside the JSON object.
"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )

    return extract_json(
        response.text
    )