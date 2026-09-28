import re


RESOURCES = [
    {
        "title": "Streamlit Documentation",
        "description": "Official documentation for creating Python-based web applications.",
        "url": "https://docs.streamlit.io",
        "keywords": ["streamlit", "ui", "frontend", "dashboard", "application"],
    },
    {
        "title": "Google Gemini API Documentation",
        "description": "Documentation for using Gemini models in Python applications.",
        "url": "https://ai.google.dev",
        "keywords": ["gemini", "ai", "llm", "language model", "api"],
    },
    {
        "title": "LangGraph Documentation",
        "description": "Documentation for building stateful and multi-step AI workflows.",
        "url": "https://langchain-ai.github.io/langgraph/",
        "keywords": ["agent", "workflow", "state", "recovery", "autonomous"],
    },
    {
        "title": "ChromaDB Documentation",
        "description": "Documentation for storing and searching vector embeddings.",
        "url": "https://docs.trychroma.com",
        "keywords": ["rag", "vector", "embedding", "retrieval", "database"],
    },
    {
        "title": "Python Subprocess Documentation",
        "description": "Documentation for executing external commands from Python.",
        "url": "https://docs.python.org/3/library/subprocess.html",
        "keywords": ["execution", "run", "test", "command", "process"],
    },
    {
        "title": "Python Zipfile Documentation",
        "description": "Documentation for creating ZIP archives using Python.",
        "url": "https://docs.python.org/3/library/zipfile.html",
        "keywords": ["zip", "download", "package", "files"],
    },
]


def retrieve_resources(project_plan, top_k=5):
    """
    Retrieve resources based on keyword matching.
    This is a simple starting point before adding embeddings.
    """

    plan_text = project_plan.lower()
    scored_resources = []

    for resource in RESOURCES:
        score = 0

        for keyword in resource["keywords"]:
            matches = re.findall(r"\b" + re.escape(keyword.lower()) + r"\b", plan_text)
            score += len(matches)

        scored_resources.append((score, resource))

    scored_resources.sort(key=lambda item: item[0], reverse=True)

    return [
        resource
        for score, resource in scored_resources[:top_k]
        if score > 0
    ]