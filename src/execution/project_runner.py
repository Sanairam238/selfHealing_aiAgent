import os
import sys
import subprocess
import ast
import time
from pathlib import Path


def discover_entrypoint(project_directory):
    """
    Find the most likely application entrypoint.
    """

    project_directory = Path(project_directory)

    preferred_files = [
        "app.py",
        "main.py",
        "run.py",
        "server.py",
    ]

    # Check root-level entrypoints first
    for filename in preferred_files:
        candidate = project_directory / filename

        if candidate.exists():
            return candidate

    # Then check common backend directories
    for directory in ["backend", "src"]:
        folder = project_directory / directory

        if folder.exists():
            for filename in preferred_files:
                candidate = folder / filename

                if candidate.exists():
                    return candidate

    # Fallback: first Python file found
    python_files = list(project_directory.rglob("*.py"))

    excluded_parts = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
    }

    python_files = [
        file
        for file in python_files
        if not any(part in excluded_parts for part in file.parts)
    ]

    if python_files:
        return python_files[0]

    return None


def detect_framework(entrypoint):
    """
    Detect framework from the actual entrypoint file.
    """

    if not entrypoint:
        return "unknown"

    try:
        content = Path(entrypoint).read_text(
            encoding="utf-8",
            errors="ignore",
        ).lower()

    except Exception:
        return "unknown"

    if "streamlit" in content:
        return "streamlit"

    if "flask" in content:
        return "flask"

    if "fastapi" in content:
        return "fastapi"

    if "django" in content:
        return "django"

    return "python"


def check_python_syntax(project_directory):
    """
    Compile every Python file to detect syntax errors.
    """

    project_directory = Path(project_directory)

    python_files = []

    excluded_parts = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
    }

    for file in project_directory.rglob("*.py"):

        if any(part in excluded_parts for part in file.parts):
            continue

        python_files.append(file)

    errors = []

    for file in python_files:

        try:

            source = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            ast.parse(
                source,
                filename=str(file),
            )

        except SyntaxError as error:

            errors.append(
                f"{file}: line {error.lineno}: {error.msg}"
            )

        except Exception as error:

            errors.append(
                f"{file}: {error}"
            )

    if errors:

        return {
            "success": False,
            "message": "Syntax errors found.",
            "errors": errors,
        }

    return {
        "success": True,
        "message": (
            f"Syntax check passed ({len(python_files)} files)."
        ),
        "errors": [],
    }


def check_dependencies(project_directory):
    """
    Check whether a dependency configuration file exists.
    """

    project_directory = Path(project_directory)

    requirements_file = (
        project_directory / "requirements.txt"
    )

    if requirements_file.exists():

        return {
            "success": True,
            "message": (
                "requirements.txt found. "
                "Dependency installation skipped."
            ),
        }

    return {
        "success": True,
        "message": (
            "No requirements.txt found. "
            "Dependency check skipped."
        ),
    }


def check_database_files(project_directory):
    """
    Perform lightweight database checks.
    """

    project_directory = Path(project_directory)

    database_paths = []

    excluded_parts = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
    }

    for file in project_directory.rglob("*.py"):

        if any(part in excluded_parts for part in file.parts):
            continue

        try:

            content = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception:
            continue

        if "sqlite3.connect" not in content:
            continue

        lines = content.splitlines()

        for line in lines:

            if "sqlite3.connect" not in line:
                continue

            for quote in ['"', "'"]:

                parts = line.split(quote)

                for part in parts:

                    if (
                        ".db" in part
                        or ".sqlite" in part
                        or ".sqlite3" in part
                    ):

                        database_paths.append(
                            project_directory / part
                        )

    unique_paths = []

    for path in database_paths:

        if path not in unique_paths:
            unique_paths.append(path)

    warnings = []

    for db_path in unique_paths:

        parent_directory = db_path.parent

        if not parent_directory.exists():

            warnings.append(
                "Database directory does not exist: "
                f"{parent_directory}"
            )

    if warnings:

        return {
            "success": False,
            "message": (
                "Database configuration problem detected."
            ),
            "errors": warnings,
        }

    return {
        "success": True,
        "message": "Database path check passed.",
        "errors": [],
    }


def run_database_smoke_test(project_directory):
    """
    Run a lightweight database initialization smoke test.
    """

    project_directory = Path(project_directory)

    database_files = list(
        project_directory.rglob("database.py")
    )

    excluded_parts = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
    }

    database_files = [
        file
        for file in database_files
        if not any(
            part in excluded_parts
            for part in file.parts
        )
    ]

    if not database_files:

        return {
            "success": True,
            "message": (
                "No database.py found. "
                "Database smoke test skipped."
            ),
            "output": "",
        }

    database_file = database_files[0]

    relative_parent = database_file.parent.relative_to(
        project_directory
    )

    module_name = database_file.stem

    command = [
        sys.executable,
        "-c",
        (
            f"import sys; "
            f"sys.path.insert(0, r'{relative_parent}'); "
            f"import {module_name}; "
            f"getattr({module_name}, 'init_db', lambda: None)()"
        ),
    ]

    try:

        result = subprocess.run(
            command,
            cwd=str(database_file.parent),
            capture_output=True,
            text=True,
            timeout=20,
        )

        output = (
            (result.stdout or "")
            + "\n"
            + (result.stderr or "")
        ).strip()

        if result.returncode != 0:

            return {
                "success": False,
                "message": "Database smoke test failed.",
                "output": output,
            }

        return {
            "success": True,
            "message": "Database smoke test passed.",
            "output": output,
        }

    except subprocess.TimeoutExpired:

        return {
            "success": False,
            "message": "Database smoke test timed out.",
            "output": (
                "Database initialization exceeded "
                "20 seconds."
            ),
        }

    except Exception as error:

        return {
            "success": False,
            "message": (
                "Database smoke test could not be executed."
            ),
            "output": str(error),
        }


def _contains_runtime_error(output):
    """
    Detect real Python/application exceptions in captured output.

    Streamlit can print warnings such as:
    'Missing Submit Button'

    Those warnings are NOT treated as application failures.

    Actual Python exceptions such as NameError, TypeError,
    AttributeError, etc. ARE treated as failures.
    """

    if not output:
        return False

    output_lower = output.lower()

    exception_markers = [
        "traceback (most recent call last):",
        "syntaxerror:",
        "nameerror:",
        "unboundlocalerror:",
        "modulenotfounderror:",
        "importerror:",
        "attributeerror:",
        "typeerror:",
        "valueerror:",
        "keyerror:",
        "indexerror:",
        "filenotfounderror:",
        "permissionerror:",
        "runtimeerror:",
        "assertionerror:",
        "zerodivisionerror:",
        "recursionerror:",
        "overflowerror:",
    ]

    return any(
        marker in output_lower
        for marker in exception_markers
    )


def _run_streamlit_and_capture(
    entrypoint,
    timeout=8,
):
    """
    Start Streamlit, allow the script to execute, then terminate
    the server and capture the complete stdout/stderr output.

    This is intentionally different from simply sleeping for a
    few seconds and immediately reading the pipes. Streamlit is a
    long-running server, so communicate() must happen after the
    process is terminated or after a timeout.
    """

    entrypoint = Path(entrypoint)

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        entrypoint.name,
        "--server.headless",
        "true",
        "--server.port",
        "8502",
        "--browser.gatherUsageStats",
        "false",
    ]

    process = None

    try:

        process = subprocess.Popen(
            command,
            cwd=str(entrypoint.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Give Streamlit enough time to:
        #
        # 1. start the server
        # 2. execute the user's script
        # 3. produce a traceback if the script is broken
        #
        time.sleep(4)

        # If Streamlit already exited, collect everything.
        if process.poll() is not None:

            stdout, stderr = process.communicate(
                timeout=3
            )

            output = (
                (stdout or "")
                + "\n"
                + (stderr or "")
            ).strip()

            return {
                "success": not _contains_runtime_error(output),
                "output": output,
                "process_exited": True,
            }

        # Streamlit is normally supposed to stay alive.
        #
        # Terminate it now so communicate() can collect all buffered
        # stdout/stderr without blocking forever.
        process.terminate()

        try:

            stdout, stderr = process.communicate(
                timeout=3
            )

        except subprocess.TimeoutExpired:

            process.kill()

            stdout, stderr = process.communicate()

        output = (
            (stdout or "")
            + "\n"
            + (stderr or "")
        ).strip()

        return {
            "success": not _contains_runtime_error(output),
            "output": output,
            "process_exited": False,
        }

    except Exception as error:

        if process is not None:

            try:
                process.kill()
                process.communicate(timeout=3)
            except Exception:
                pass

        return {
            "success": False,
            "output": str(error),
            "process_exited": True,
        }


def check_application_startup(
    project_directory,
    timeout=8,
):
    """
    Start the detected application briefly to verify startup.

    Streamlit applications receive two levels of validation:

    1. Direct Python import check for import-time failures.
    2. Actual Streamlit execution to detect runtime errors that
       only occur when Streamlit executes the page.
    """

    project_directory = Path(project_directory)

    entrypoint = discover_entrypoint(
        project_directory
    )

    if not entrypoint:

        return {
            "success": False,
            "message": "No application entrypoint found.",
            "output": "",
        }

    framework = detect_framework(
        entrypoint
    )

    process = None

    try:

        # =========================================================
        # STREAMLIT PREFLIGHT IMPORT CHECK
        # =========================================================

        if framework == "streamlit":

            import_command = [
                sys.executable,
                "-c",
                f"import {entrypoint.stem}",
            ]

            import_result = subprocess.run(
                import_command,
                cwd=str(entrypoint.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

            import_output = (
                (import_result.stdout or "")
                + "\n"
                + (import_result.stderr or "")
            ).strip()

            if import_result.returncode != 0:

                return {
                    "success": False,
                    "message": (
                        "Application import failed."
                    ),
                    "output": import_output,
                    "entrypoint": str(entrypoint),
                    "framework": framework,
                }

            # -----------------------------------------------------
            # IMPORTANT:
            #
            # A normal Python import is not enough for Streamlit.
            # Streamlit executes the script through its own runtime.
            #
            # Therefore we STILL run the actual Streamlit app.
            # -----------------------------------------------------

            streamlit_result = (
                _run_streamlit_and_capture(
                    entrypoint,
                    timeout=timeout,
                )
            )

            streamlit_output = (
                streamlit_result.get(
                    "output",
                    ""
                )
            )

            if not streamlit_result["success"]:

                return {
                    "success": False,
                    "message": (
                        "Application runtime error detected."
                    ),
                    "output": streamlit_output,
                    "entrypoint": str(entrypoint),
                    "framework": framework,
                }

            return {
                "success": True,
                "message": (
                    "Streamlit application started "
                    "and executed successfully."
                ),
                "output": streamlit_output,
                "entrypoint": str(entrypoint),
                "framework": framework,
            }

        # =========================================================
        # FLASK
        # =========================================================

        if framework == "flask":

            command = [
                sys.executable,
                "-c",
                (
                    "from app import app; "
                    "app.run("
                    "host='127.0.0.1', "
                    "port=5001, "
                    "debug=False, "
                    "use_reloader=False"
                    ")"
                ),
            ]

        # =========================================================
        # OTHER PYTHON APPLICATIONS
        # =========================================================

        else:

            command = [
                sys.executable,
                entrypoint.name,
            ]

        # =========================================================
        # START APPLICATION
        # =========================================================

        process = subprocess.Popen(
            command,
            cwd=str(entrypoint.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        time.sleep(3)

        # =========================================================
        # APPLICATION EXITED
        # =========================================================

        if process.poll() is not None:

            stdout, stderr = process.communicate(
                timeout=3
            )

            output = (
                (stdout or "")
                + "\n"
                + (stderr or "")
            ).strip()

            return {
                "success": False,
                "message": (
                    "Application failed during startup."
                ),
                "output": output,
                "entrypoint": str(entrypoint),
                "framework": framework,
            }

        # =========================================================
        # APPLICATION STILL RUNNING
        # =========================================================

        process.terminate()

        try:

            stdout, stderr = process.communicate(
                timeout=3
            )

        except subprocess.TimeoutExpired:

            process.kill()

            stdout, stderr = process.communicate()

        output = (
            (stdout or "")
            + "\n"
            + (stderr or "")
        ).strip()

        if _contains_runtime_error(output):

            return {
                "success": False,
                "message": (
                    "Application runtime error detected."
                ),
                "output": output,
                "entrypoint": str(entrypoint),
                "framework": framework,
            }

        return {
            "success": True,
            "message": (
                "Application started successfully."
            ),
            "output": output,
            "entrypoint": str(entrypoint),
            "framework": framework,
        }

    except Exception as error:

        if process is not None:

            try:
                process.kill()
                process.communicate(timeout=3)
            except Exception:
                pass

        return {
            "success": False,
            "message": (
                "Application startup check failed."
            ),
            "output": str(error),
            "entrypoint": str(entrypoint),
            "framework": framework,
        }


def run_project_checks(project_directory):
    """
    Run the complete project validation pipeline.
    """

    print("\n--- PROJECT VALIDATION ---")

    project_directory = Path(
        project_directory
    )

    # --------------------------------------------------
    # 1. Syntax
    # --------------------------------------------------

    print("Checking Python syntax...")

    syntax_result = check_python_syntax(
        project_directory
    )

    print(syntax_result["message"])

    if not syntax_result["success"]:

        return {
            "success": False,
            "stage": "syntax",
            "output": "\n".join(
                syntax_result["errors"]
            ),
        }

    # --------------------------------------------------
    # 2. Dependencies
    # --------------------------------------------------

    print(
        "Checking dependency configuration..."
    )

    dependency_result = check_dependencies(
        project_directory
    )

    print(
        dependency_result["message"]
    )

    # --------------------------------------------------
    # 3. Database path configuration
    # --------------------------------------------------

    print(
        "Checking database configuration..."
    )

    database_config_result = (
        check_database_files(
            project_directory
        )
    )

    print(
        database_config_result["message"]
    )

    if not database_config_result["success"]:

        return {
            "success": False,
            "stage": "database",
            "output": "\n".join(
                database_config_result["errors"]
            ),
        }

    # --------------------------------------------------
    # 4. Database smoke test
    # --------------------------------------------------

    print(
        "Running database smoke test..."
    )

    database_smoke_result = (
        run_database_smoke_test(
            project_directory
        )
    )

    print(
        database_smoke_result["message"]
    )

    if not database_smoke_result["success"]:

        return {
            "success": False,
            "stage": "database",
            "output": database_smoke_result["output"],
        }

    # --------------------------------------------------
    # 5. Application startup/runtime
    # --------------------------------------------------

    print(
        "Checking application startup..."
    )

    startup_result = (
        check_application_startup(
            project_directory
        )
    )

    print(
        startup_result["message"]
    )

    if not startup_result["success"]:

        return {
            "success": False,
            "stage": "application",
            "output": startup_result["output"],
            "entrypoint": startup_result.get(
                "entrypoint"
            ),
            "framework": startup_result.get(
                "framework"
            ),
        }

    # --------------------------------------------------
    # Everything passed
    # --------------------------------------------------

    print(
        "Project validation PASSED."
    )

    return {
        "success": True,
        "stage": "validation",
        "output": "All project checks passed.",
        "entrypoint": startup_result.get(
            "entrypoint"
        ),
        "framework": startup_result.get(
            "framework"
        ),
    }