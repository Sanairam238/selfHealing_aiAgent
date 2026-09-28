import socket
import subprocess
import sys
import time
from pathlib import Path


COMMAND_TIMEOUT = 30
APPLICATION_STARTUP_TIMEOUT = 8

EXCLUDED_DIRECTORIES = {
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".git",
    "node_modules",
}


def run_command(command, cwd, timeout=COMMAND_TIMEOUT):
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "timed_out": False,
        }

    except subprocess.TimeoutExpired as error:
        return {
            "success": False,
            "returncode": None,
            "stdout": str(error.stdout or ""),
            "stderr": str(error.stderr or ""),
            "timed_out": True,
        }

    except Exception as error:
        return {
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(error),
            "timed_out": False,
        }


def discover_python_files(project_directory):
    project_path = Path(project_directory).resolve()

    files = []

    for path in project_path.rglob("*.py"):
        relative_parts = path.relative_to(project_path).parts

        if any(
            part in EXCLUDED_DIRECTORIES
            for part in relative_parts
        ):
            continue

        files.append(path.resolve())

    return sorted(files)


def check_python_syntax(project_directory):
    project_path = Path(project_directory).resolve()

    python_files = discover_python_files(project_path)

    if not python_files:
        return {
            "success": True,
            "checked_files": 0,
            "message": "No Python files found.",
        }

    failures = []

    for python_file in python_files:
        absolute_file = str(python_file)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                absolute_file,
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            failures.append(
                {
                    "file": str(
                        python_file.relative_to(project_path)
                    ),
                    "error": (
                        result.stderr.strip()
                        or result.stdout.strip()
                    ),
                }
            )

    if failures:
        return {
            "success": False,
            "checked_files": len(python_files),
            "failures": failures,
            "message": "Python syntax validation failed.",
        }

    return {
        "success": True,
        "checked_files": len(python_files),
        "message": "Python syntax validation passed.",
    }


def find_requirements_file(project_directory):
    project_path = Path(project_directory).resolve()

    for filename in [
        "requirements.txt",
        "requirements-dev.txt",
    ]:
        path = project_path / filename

        if path.exists():
            return path

    return None


def check_requirements_file(project_directory):
    requirements = find_requirements_file(project_directory)

    if requirements is None:
        return {
            "success": True,
            "message": "No requirements.txt found. Dependency installation skipped.",
        }

    try:
        content = requirements.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()

        if not content:
            return {
                "success": False,
                "message": "requirements.txt is empty.",
            }

        return {
            "success": True,
            "message": (
                "requirements.txt found. "
                "Dependency installation skipped."
            ),
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Could not read requirements.txt: {error}",
        }


def discover_test_files(project_directory):
    project_path = Path(project_directory).resolve()

    tests = []

    for path in project_path.rglob("*.py"):
        relative_parts = path.relative_to(project_path).parts

        if any(
            part in EXCLUDED_DIRECTORIES
            for part in relative_parts
        ):
            continue

        filename = path.name.lower()

        if (
            filename.startswith("test_")
            or filename.endswith("_test.py")
        ):
            tests.append(path)

    return sorted(tests)


def run_tests(project_directory):
    test_files = discover_test_files(project_directory)

    if not test_files:
        return {
            "success": True,
            "tests_found": 0,
            "message": "No test files found. Tests skipped.",
        }

    result = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
        ],
        Path(project_directory).resolve(),
        timeout=20,
    )

    if not result["success"]:
        return {
            "success": False,
            "tests_found": len(test_files),
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "message": (
                "Tests timed out."
                if result["timed_out"]
                else "Tests failed."
            ),
        }

    return {
        "success": True,
        "tests_found": len(test_files),
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "message": "Tests passed.",
    }


def find_free_port():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    sock.bind(("127.0.0.1", 0))

    port = sock.getsockname()[1]

    sock.close()

    return port


def detect_framework(entrypoint):
    """
    Detect the framework used by the specific application entrypoint.

    This is intentionally entrypoint-specific because a project can contain
    both a Flask backend and a Streamlit frontend.
    """

    entrypoint = Path(entrypoint).resolve()

    try:
        content = entrypoint.read_text(
            encoding="utf-8",
            errors="replace",
        ).lower()
    except Exception:
        return "python"

    # Check FastAPI first because it normally exposes an ASGI app.
    if (
        "from fastapi import" in content
        or "import fastapi" in content
    ):
        return "fastapi"

    # Flask backend.
    if (
        "from flask import" in content
        or "import flask" in content
        or "flask(" in content
    ):
        return "flask"

    # Streamlit frontend.
    if (
        "import streamlit" in content
        or "from streamlit" in content
        or "st." in content
    ):
        return "streamlit"

    return "python"


def discover_entrypoint(project_directory):
    project_path = Path(project_directory).resolve()

    preferred_names = [
        "app.py",
        "main.py",
        "run.py",
        "server.py",
    ]

    candidates = []

    # Prefer root-level entrypoints.
    for filename in preferred_names:
        root_file = project_path / filename

        if root_file.exists():
            candidates.append(root_file.resolve())

    # Then search subdirectories.
    for filename in preferred_names:
        for path in project_path.rglob(filename):

            relative_parts = path.relative_to(project_path).parts

            if any(
                part in EXCLUDED_DIRECTORIES
                for part in relative_parts
            ):
                continue

            absolute_path = path.resolve()

            if absolute_path not in candidates:
                candidates.append(absolute_path)

    if not candidates:
        return None

    # Prefer backend entrypoints when both frontend and backend
    # applications exist.
    backend_candidates = [
        path
        for path in candidates
        if "backend" in path.relative_to(project_path).parts
    ]

    if backend_candidates:
        return backend_candidates[0]

    return candidates[0]

def start_application(project_directory):
    project_path = Path(project_directory).resolve()

    entrypoint = discover_entrypoint(project_path)

    if entrypoint is None:
        return {
            "success": True,
            "checked": False,
            "message": "No application entry point found.",
        }

    # Detect framework from the actual entrypoint.
    framework = detect_framework(entrypoint)

    relative_entrypoint = entrypoint.relative_to(project_path)

    port = find_free_port()

    # ---------------------------------------------------------
    # Build command
    # ---------------------------------------------------------

    if framework == "streamlit":

        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(relative_entrypoint),
            "--server.headless",
            "true",
            "--server.port",
            str(port),
        ]

        working_directory = project_path

    elif framework == "fastapi":

        module_name = (
            relative_entrypoint
            .with_suffix("")
            .as_posix()
            .replace("/", ".")
        )

        command = [
            sys.executable,
            "-m",
            "uvicorn",
            f"{module_name}:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

        working_directory = project_path

    elif framework == "flask":

        # IMPORTANT:
        # Do NOT execute "python backend/app.py" directly.
        #
        # The generated Flask applications may use:
        #
        #     app.run(debug=True)
        #
        # which starts Flask's Windows reloader.
        #
        # Instead, import the Flask app and start it ourselves
        # with debug=False and use_reloader=False.
        #
        # This makes application startup validation deterministic.

        backend_directory = entrypoint.parent

        command = [
            sys.executable,
            "-c",
            (
                "from app import app; "
                f"app.run(host='127.0.0.1', port={port}, "
                "debug=False, use_reloader=False)"
            ),
        ]

        working_directory = backend_directory

    else:

        command = [
            sys.executable,
            str(relative_entrypoint),
        ]

        working_directory = project_path

    # ---------------------------------------------------------
    # Start application
    # ---------------------------------------------------------

    try:

        process = subprocess.Popen(
            command,
            cwd=str(working_directory),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    except Exception as error:

        return {
            "success": False,
            "entrypoint": str(relative_entrypoint),
            "framework": framework,
            "message": f"Could not start application: {error}",
        }

    start_time = time.time()

    # ---------------------------------------------------------
    # Monitor startup
    # ---------------------------------------------------------

    while time.time() - start_time < APPLICATION_STARTUP_TIMEOUT:

        returncode = process.poll()

        # -----------------------------------------------------
        # Application exited before startup timeout.
        # -----------------------------------------------------

        if returncode is not None:

            try:
                stderr = process.stderr.read() if process.stderr else ""
            except Exception:
                stderr = ""

            output = stderr.strip()

            return {
                "success": returncode == 0,
                "entrypoint": str(relative_entrypoint),
                "framework": framework,
                "returncode": returncode,
                "output": output,
                "message": (
                    "Application exited successfully."
                    if returncode == 0
                    else "Application failed during startup."
                ),
            }

        time.sleep(0.25)

    # ---------------------------------------------------------
    # Application survived startup window.
    # ---------------------------------------------------------

    try:

        process.terminate()

        try:
            process.wait(timeout=3)

        except subprocess.TimeoutExpired:

            process.kill()
            process.wait(timeout=3)

    except Exception:
        pass

    return {
        "success": True,
        "entrypoint": str(relative_entrypoint),
        "framework": framework,
        "returncode": 0,
        "output": "",
        "message": (
            "Application started successfully "
            "and passed the startup check."
        ),
    }

def run_application(project_directory):
    return start_application(project_directory)


def run_project_checks(project_directory):

    project_path = Path(project_directory).resolve()

    if not project_path.exists():

        return {
            "success": False,
            "stage": "project",
            "summary": (
                f"Project directory does not exist: "
                f"{project_path}"
            ),
        }

    print("Checking Python syntax...")

    syntax = check_python_syntax(project_path)

    if not syntax["success"]:

        return {
            "success": False,
            "stage": "syntax",
            "syntax": syntax,
            "summary": syntax["message"],
        }

    print(
        f"Syntax check passed "
        f"({syntax['checked_files']} files)."
    )

    print("Checking dependency configuration...")

    dependencies = check_requirements_file(project_path)

    if not dependencies["success"]:

        return {
            "success": False,
            "stage": "dependencies",
            "syntax": syntax,
            "dependencies": dependencies,
            "summary": dependencies["message"],
        }

    print(dependencies["message"])

    print("Checking tests...")

    tests = run_tests(project_path)

    if not tests["success"]:

        summary = "\n".join(
            part
            for part in [
                tests.get("stdout", ""),
                tests.get("stderr", ""),
                tests.get("message", ""),
            ]
            if part
        )

        return {
            "success": False,
            "stage": "tests",
            "syntax": syntax,
            "dependencies": dependencies,
            "tests": tests,
            "summary": summary,
        }

    print(tests["message"])

    print("Checking application startup...")

    application = run_application(project_path)

    if not application["success"]:

        summary = "\n".join(
            part
            for part in [
                application.get("output", ""),
                application.get("message", ""),
            ]
            if part
        )

        return {
            "success": False,
            "stage": "application",
            "syntax": syntax,
            "dependencies": dependencies,
            "tests": tests,
            "application": application,
            "summary": summary,
        }

    print(application["message"])

    return {
        "success": True,
        "stage": "complete",
        "syntax": syntax,
        "dependencies": dependencies,
        "tests": tests,
        "application": application,
        "summary": "All fast project checks passed.",
    }