import os

import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel("gemini-3.5-flash-lite")


def generate_project_blueprint(
    project_name,
    project_description,
    project_plan,
    resources,
):
    resource_text = "\n".join(
        [
            f"- {resource['title']}: {resource['description']} "
            f"({resource['url']})"
            for resource in resources
        ]
    )

    prompt = f"""
You are a senior software architect.

Create a detailed final project blueprint using the information below.

PROJECT NAME:
{project_name}

PROJECT DESCRIPTION:
{project_description}

APPROVED PROJECT PLAN:
{project_plan}

APPROVED RESOURCES:
{resource_text}

The blueprint must include:

1. Project overview
2. Main objectives
3. Features and modules
4. Recommended technology stack
5. System architecture
6. Database design
7. API requirements
8. Frontend pages
9. Backend responsibilities
10. Folder structure
11. Execution and testing strategy
12. Error handling
13. Self-healing and recovery strategy
14. Human approval checkpoints
15. Development sequence

Write the blueprint in a clear, human-readable format.
Do not generate source code yet.
"""

    response = model.generate_content(prompt)

    return response.text