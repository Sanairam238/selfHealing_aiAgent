import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

import streamlit as st

from src.agents.planner import generate_project_plan, modify_project_plan
from src.rag.resource_retriever import retrieve_resources
from src.agents.blueprint import generate_project_blueprint
from src.generators.code_generator import generate_project_files
from src.generators.project_saver import (
    save_project_files,
    create_project_zip,
    create_zip_bytes,
)
from src.recovery.recovery_manager import run_with_self_healing


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Self-Healing AI Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 4rem;
    }

    .hero {
        padding: 1.2rem 0 1.5rem 0;
    }

    .hero h1 {
        margin-bottom: .25rem;
    }

    .hero p {
        color: #8b8b95;
        margin-top: 0;
    }

    .module-card {
        border: 1px solid rgba(150,150,160,.16);
        border-radius: 14px;
        padding: 1rem;
        margin-bottom: .8rem;
        background: rgba(150,150,160,.035);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "project_name": "",
    "project_description": "",
    "project_plan": None,
    "plan_approved": False,
    "resources": [],
    "resources_confirmed": False,
    "project_blueprint": None,

    # ONE continuous chat
    "project_chat_messages": [],

    "blueprint_approved": False,

    "generated_files": [],
    "zip_bytes": None,

    "recovery_result": None,
    "project_directory": None,
    "saved_files": [],

    "validation_status": None,
    "validation_error": None,

    "uploaded_project_path": None,
    "uploaded_project_name": None,
    "uploaded_recovery_result": None,
    "uploaded_validation_status": None,
    "uploaded_validation_error": None,

    "recovery_history": [],

    "active_module": "Dashboard",
}


for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# HELPERS
# ============================================================

def safe_project_name(project_name: str) -> str:
    name = str(project_name).strip()
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "Generated_Project"


def plan_to_resource_query(plan):
    if isinstance(plan, str):
        return plan

    if isinstance(plan, dict):
        parts = []

        summary = plan.get("summary")
        detailed_plan = plan.get("detailed_plan")

        if isinstance(summary, list):
            parts.extend(str(item) for item in summary)
        elif summary:
            parts.append(str(summary))

        if detailed_plan:
            parts.append(str(detailed_plan))

        if parts:
            return "\n".join(parts)

        return json.dumps(plan, ensure_ascii=False)

    if isinstance(plan, list):
        return "\n".join(str(item) for item in plan)

    return str(plan)


def display_plan_summary(plan):
    if isinstance(plan, dict):
        summary = plan.get("summary", [])

        if isinstance(summary, list):
            for item in summary:
                st.markdown(f"- {item}")
        else:
            st.markdown(str(summary))
    else:
        st.markdown(str(plan))


def display_detailed_plan(plan):
    if isinstance(plan, dict):
        st.markdown(
            plan.get(
                "detailed_plan",
                "No detailed plan available.",
            )
        )
    else:
        st.markdown(str(plan))


def language_for_file(path: str) -> str:
    suffix = Path(path).suffix.lower()

    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "text")


def add_recovery_history(project_name, result, source="Generated Project"):
    st.session_state.recovery_history.append(
        {
            "project_name": project_name,
            "source": source,
            "success": (
                bool(result.get("success"))
                if isinstance(result, dict)
                else False
            ),
            "repair_attempts": (
                result.get("repair_attempts", 0)
                if isinstance(result, dict)
                else 0
            ),
            "history": (
                result.get("history", [])
                if isinstance(result, dict)
                else []
            ),
        }
    )


def reset_generated_project_state():
    for key in [
        "project_plan",
        "plan_approved",
        "resources",
        "resources_confirmed",
        "project_blueprint",
        "blueprint_approved",
        "generated_files",
        "zip_bytes",
        "recovery_result",
        "project_directory",
        "saved_files",
        "validation_status",
        "validation_error",
        "project_chat_messages",
    ]:
        st.session_state[key] = DEFAULTS[key]


def reset_everything():
    for key, value in DEFAULTS.items():
        if key == "recovery_history":
            continue

        st.session_state[key] = value

    st.rerun()


def reset_uploaded_state():
    st.session_state.uploaded_project_path = None
    st.session_state.uploaded_project_name = None
    st.session_state.uploaded_recovery_result = None
    st.session_state.uploaded_validation_status = None
    st.session_state.uploaded_validation_error = None


# ============================================================
# ZIP EXTRACTION
# ============================================================

def safe_extract_zip(uploaded_file, destination: Path):
    """
    Safely extract a ZIP without allowing paths to escape
    the destination directory.

    If the ZIP contains one wrapper folder, its contents are
    flattened so the actual project remains directly inside
    the uploaded project directory.
    """

    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(uploaded_file) as archive:

        for member in archive.infolist():

            member_path = Path(member.filename)

            # Ignore macOS metadata
            if "__MACOSX" in member_path.parts:
                continue

            target = (destination / member.filename).resolve()
            destination_resolved = destination.resolve()

            if (
                target != destination_resolved
                and destination_resolved not in target.parents
            ):
                raise ValueError(
                    "Unsafe ZIP file: it contains a path outside "
                    "the project directory."
                )

        archive.extractall(destination)

    # Remove macOS metadata if present
    macos_folder = destination / "__MACOSX"

    if macos_folder.exists():
        shutil.rmtree(macos_folder, ignore_errors=True)

    children = list(destination.iterdir())

    # If ZIP contains exactly one folder, flatten it.
    if len(children) == 1 and children[0].is_dir():

        wrapper = children[0]

        for item in wrapper.iterdir():

            target = destination / item.name

            if target.exists():
                if target.is_dir():
                    shutil.copytree(
                        item,
                        target,
                        dirs_exist_ok=True,
                    )
                    shutil.rmtree(item)
                else:
                    target.unlink()
                    shutil.move(str(item), str(target))
            else:
                shutil.move(str(item), str(target))

        wrapper.rmdir()

    return destination


def save_uploaded_project(uploaded_file):
    """
    Save uploaded projects directly inside workspace/.

    ZIP:

        workspace/
        └── project_name_uniqueid/
            ├── app.py
            ├── requirements.txt
            └── ...

    Single Python file:

        workspace/
        └── project_name_uniqueid/
            └── app.py
    """

    base = Path("workspace")
    base.mkdir(parents=True, exist_ok=True)

    safe_name = safe_project_name(
        Path(uploaded_file.name).stem
    )

    project_dir = (
        base
        / f"{safe_name}_{uuid.uuid4().hex[:8]}"
    )

    project_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if uploaded_file.name.lower().endswith(".zip"):

        project_dir = safe_extract_zip(
            uploaded_file,
            project_dir,
        )

    elif uploaded_file.name.lower().endswith(".py"):

        (
            project_dir / "app.py"
        ).write_bytes(
            uploaded_file.getbuffer()
        )

    else:

        raise ValueError(
            "Please upload a .zip project or a single .py file."
        )

    return project_dir


def history_by_type(history, item_type):
    return [
        item
        for item in history
        if item.get("type") == item_type
    ]


# ============================================================
# RECOVERY TRACE HELPERS
# ============================================================

def _clean_label(value):
    if value is None:
        return "Unknown"

    return (
        str(value)
        .replace("_", " ")
        .replace("-", " ")
        .title()
    )


def _extract_validation_error(validation):
    """
    Extract the actual validation error from a validation
    history entry.
    """

    if not isinstance(validation, dict):
        return None

    result = validation.get("result", {})

    if isinstance(result, dict):

        for key in [
            "error",
            "message",
            "stderr",
            "exception",
            "details",
        ]:
            value = result.get(key)

            if value:
                return value

    for key in [
        "error",
        "message",
        "stderr",
        "exception",
        "details",
    ]:
        value = validation.get(key)

        if value:
            return value

    return None


def _validation_success(validation):
    if not isinstance(validation, dict):
        return False

    result = validation.get("result", {})

    if isinstance(result, dict):
        return bool(result.get("success"))

    return bool(validation.get("success"))


def build_recovery_cycles(history):
    """
    Reconstruct actual recovery cycles from the chronological
    history instead of matching validation/classification/
    strategy/repair entries by list index.

    Expected flow:

        validation
        classification
        strategy
        repair
        validation
        classification
        strategy
        repair
        validation
    """

    cycles = []

    current_cycle = None

    for event in history:

        event_type = event.get("type")

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if event_type == "validation":

            if current_cycle is not None:

                current_cycle["revalidation"] = event

                cycles.append(current_cycle)

                current_cycle = None

            validation_success = _validation_success(event)

            # A failed validation starts a recovery cycle.
            if not validation_success:

                current_cycle = {
                    "validation": event,
                    "classification": None,
                    "strategy": None,
                    "repair": None,
                    "revalidation": None,
                }

        # ----------------------------------------------------
        # CLASSIFICATION
        # ----------------------------------------------------

        elif (
            event_type == "classification"
            and current_cycle is not None
        ):

            current_cycle["classification"] = event

        # ----------------------------------------------------
        # STRATEGY
        # ----------------------------------------------------

        elif (
            event_type == "strategy"
            and current_cycle is not None
        ):

            current_cycle["strategy"] = event

        # ----------------------------------------------------
        # REPAIR
        # ----------------------------------------------------

        elif (
            event_type == "repair"
            and current_cycle is not None
        ):

            current_cycle["repair"] = event

    # Handle incomplete final cycle
    if current_cycle is not None:
        cycles.append(current_cycle)

    return cycles


def render_recovery_trace(result):
    """
    Render the recovery process chronologically.

    This avoids the previous problem where validation #3 could
    incorrectly be displayed with classification #3 or repair
    #3 even when those events belonged to different cycles.
    """

    if not isinstance(result, dict):
        return

    history = result.get("history", [])

    if not isinstance(history, list):
        history = []

    validation_items = history_by_type(
        history,
        "validation",
    )

    repair_items = history_by_type(
        history,
        "repair",
    )

    repair_attempts = result.get(
        "repair_attempts",
        len(repair_items),
    )

    success = bool(result.get("success"))

    cycles = build_recovery_cycles(history)

    # ========================================================
    # OVERALL RESULT
    # ========================================================

    st.markdown("### 🩺 Recovery Result")

    if success and repair_attempts > 0:

        st.success(
            f"✅ Project recovered successfully after "
            f"{repair_attempts} repair attempt"
            f"{'s' if repair_attempts != 1 else ''}."
        )

    elif success and repair_attempts == 0:

        st.success(
            "✅ Project is already valid — "
            "no repair was required."
        )

    else:

        st.warning(
            "⚠️ Recovery attempts finished, but the "
            "project still needs attention."
        )

    # ========================================================
    # SUMMARY METRICS
    # ========================================================

    metric_cols = st.columns(4)

    with metric_cols[0]:

        st.metric(
            "Validations",
            len(validation_items),
        )

    with metric_cols[1]:

        st.metric(
            "Repair cycles",
            repair_attempts,
        )

    with metric_cols[2]:

        latest_error_type = None

        for cycle in reversed(cycles):

            classification = cycle.get(
                "classification"
            )

            if classification:

                latest_error_type = classification.get(
                    "error_type"
                )

                if latest_error_type:
                    break

        st.metric(
            "Latest error",
            _clean_label(latest_error_type)
            if latest_error_type
            else "None",
        )

    with metric_cols[3]:

        if success and repair_attempts > 0:
            result_text = "Recovered"

        elif success:
            result_text = "Already valid"

        else:
            result_text = "Needs attention"

        st.metric(
            "Result",
            result_text,
        )

    # ========================================================
    # TECHNICAL TRACE
    # ========================================================

    st.markdown("### 🔍 Technical Recovery Trace")

    st.caption(
        "Validation → Error Detection → Classification → "
        "Recovery Strategy → Repair → Re-validation"
    )

    # ========================================================
    # NO ERRORS
    # ========================================================

    if success and repair_attempts == 0:

        st.success(
            "🎉 The uploaded/generated project passed "
            "validation on the first attempt."
        )

        if validation_items:

            first_validation = validation_items[0]

            if _validation_success(first_validation):

                st.markdown(
                    "#### 🔎 Initial Validation"
                )

                st.success(
                    "✅ Validation passed. "
                    "No recovery cycle was necessary."
                )

    # ========================================================
    # ACTUAL RECOVERY CYCLES
    # ========================================================

    for index, cycle in enumerate(
        cycles,
        start=1,
    ):

        validation = cycle.get(
            "validation"
        )

        classification = cycle.get(
            "classification"
        )

        strategy = cycle.get(
            "strategy"
        )

        repair = cycle.get(
            "repair"
        )

        revalidation = cycle.get(
            "revalidation"
        )

        st.markdown(
            f"### 🔄 Recovery Cycle {index}"
        )

        # ----------------------------------------------------
        # 1. ERROR DETECTED
        # ----------------------------------------------------

        st.markdown(
            "**1️⃣ Error detected**"
        )

        actual_error = _extract_validation_error(
            validation
        )

        if actual_error:

            st.error(
                "❌ Validation failed."
            )

            st.markdown(
                "**Actual error:**"
            )

            st.code(
                str(actual_error),
                language="text",
            )

        else:

            st.error(
                "❌ Validation failed — "
                "error details were not returned."
            )

        # ----------------------------------------------------
        # 2. CLASSIFICATION
        # ----------------------------------------------------

        st.markdown(
            "**2️⃣ Error classification**"
        )

        if classification:

            error_type = classification.get(
                "error_type",
                "unknown_error",
            )

            confidence = classification.get(
                "confidence"
            )

            message = classification.get(
                "message"
            )

            st.info(
                _clean_label(error_type)
            )

            if confidence is not None:

                st.caption(
                    f"Classification confidence: "
                    f"{confidence}"
                )

            if message:

                st.markdown(
                    "**Classifier explanation:**"
                )

                st.code(
                    str(message),
                    language="text",
                )

        else:

            st.warning(
                "No classification event was recorded."
            )

        # ----------------------------------------------------
        # 3. RECOVERY STRATEGY
        # ----------------------------------------------------

        st.markdown(
            "**3️⃣ Recovery strategy**"
        )

        recovery_strategy = None

        if strategy:

            recovery_strategy = strategy.get(
                "recovery_strategy"
            )

        if not recovery_strategy and repair:

            recovery_strategy = repair.get(
                "recovery_strategy"
            )

        if recovery_strategy:

            st.info(
                _clean_label(
                    recovery_strategy
                )
            )

        else:

            st.info(
                "Analyze With Gemini"
            )

        # ----------------------------------------------------
        # 4. SELF HEALING
        # ----------------------------------------------------

        st.markdown(
            "**4️⃣ Gemini self-healing repair**"
        )

        if repair:

            repair_result = repair.get(
                "result"
            )

            repair_message = repair.get(
                "message"
            )

            if isinstance(
                repair_result,
                dict,
            ):

                repair_success = repair_result.get(
                    "success"
                )

                if repair_success is not None:

                    if repair_success:
                        st.success(
                            "🤖 Gemini repair completed successfully."
                        )
                    else:
                        st.warning(
                            "⚠️ Gemini repair step reported failure."
                        )

                else:

                    st.success(
                        "🤖 Gemini repair step completed."
                    )

            elif repair_message:

                st.success(
                    str(repair_message)
                )

            else:

                st.success(
                    "🤖 Gemini repair step completed."
                )

        else:

            st.warning(
                "No repair event was recorded for this cycle."
            )

        # ----------------------------------------------------
        # 5. RECOVERY PATH
        # ----------------------------------------------------

        st.markdown(
            "**5️⃣ Recovery path**"
        )

        recovery_path = None

        if strategy:

            recovery_path = strategy.get(
                "recovery_path"
            )

        if not recovery_path and repair:

            recovery_path = repair.get(
                "recovery_path"
            )

        if recovery_path:

            if isinstance(
                recovery_path,
                list,
            ):

                st.code(
                    " → ".join(
                        _clean_label(step)
                        for step in recovery_path
                    ),
                    language="text",
                )

            else:

                st.code(
                    str(recovery_path),
                    language="text",
                )

        else:

            st.code(
                "Error → Recovery Strategy → "
                "Analyze With Gemini → Revalidate",
                language="text",
            )

        # ----------------------------------------------------
        # 6. RE-VALIDATION
        # ----------------------------------------------------

        st.markdown(
            "**6️⃣ Re-validation**"
        )

        if revalidation:

            if _validation_success(
                revalidation
            ):

                st.success(
                    "✅ Re-validation passed."
                )

            else:

                st.error(
                    "❌ Re-validation failed — "
                    "the next recovery cycle will "
                    "diagnose the current error."
                )

                next_error = _extract_validation_error(
                    revalidation
                )

                if next_error:

                    st.code(
                        str(next_error),
                        language="text",
                    )

        else:

            st.info(
                "The repaired project was sent back "
                "through the validation pipeline."
            )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    if validation_items:

        last_validation = validation_items[-1]

        if _validation_success(
            last_validation
        ):

            st.markdown(
                "### 🎯 Final Validation"
            )

            st.success(
                "✅ Project passed the validation pipeline."
            )

        elif not cycles:

            st.markdown(
                "### 🎯 Final Validation"
            )

            st.error(
                "❌ Project did not pass validation."
            )

    # ========================================================
    # RECOVERY PATH SUMMARY
    # ========================================================

    if repair_items:

        st.markdown(
            "### 🛠️ Recovery Paths Used"
        )

        for index, repair in enumerate(
            repair_items,
            start=1,
        ):

            error_type = repair.get(
                "error_type",
                "unknown_error",
            )

            strategy = repair.get(
                "recovery_strategy",
                "analyze_with_gemini",
            )

            st.code(
                f"Cycle {index}: "
                f"{_clean_label(error_type)} "
                f"→ "
                f"{_clean_label(strategy)} "
                f"→ Analyze With Gemini "
                f"→ Revalidate",
                language="text",
            )

    # ========================================================
    # RAW LOGS
    # ========================================================

    st.markdown(
        "### 📋 Raw Validation / Recovery Logs"
    )

    st.json(history)


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

st.sidebar.title(
    "🤖 Self-Healing AI Agent"
)

st.sidebar.caption(
    "Autonomous software planning, generation, "
    "validation and recovery"
)

modules = [
    "🏠 Dashboard",
    "🏗️ Project Builder",
    "📁 Workspace",
    "🩺 Self-Healing",
    "📤 Re-check Edited Project",
    "📜 Recovery History",
]

selected = st.sidebar.radio(
    "Modules",
    modules,
    index=(
        modules.index(
            st.session_state.active_module
        )
        if st.session_state.active_module in modules
        else 0
    ),
)

st.session_state.active_module = selected

st.sidebar.divider()

if st.sidebar.button(
    "↻ Start New Project",
    use_container_width=True,
):
    reset_everything()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        <h1>🤖 Self-Healing AI Agent</h1>
        <p>
            Autonomous software planning, generation,
            validation, recovery, and re-checking.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DASHBOARD
# ============================================================

if selected == "🏠 Dashboard":

    st.subheader("System Dashboard")

    generated_count = (
        1
        if st.session_state.project_directory
        else 0
    )

    recovered_count = sum(
        1
        for item in st.session_state.recovery_history
        if item["success"]
        and item["repair_attempts"] > 0
    )

    total_repairs = sum(
        item["repair_attempts"]
        for item in st.session_state.recovery_history
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Generated project",
        generated_count,
    )

    c2.metric(
        "Successful recoveries",
        recovered_count,
    )

    c3.metric(
        "Recovery attempts",
        total_repairs,
    )

    c4.metric(
        "Recovery sessions",
        len(
            st.session_state.recovery_history
        ),
    )

    st.markdown("### Workflow")

    st.info(
        "Requirement → Planner → Blueprint → "
        "Code Generator → Validator → Error Classifier → "
        "RAG → Recovery Strategy → Gemini Self-Healer → "
        "Re-validation"
    )

    st.markdown(
        "### Two ways to use the agent"
    )

    left, right = st.columns(2)

    with left:

        st.markdown(
            "#### 🏗️ Generate a project"
        )

        st.write(
            "Create a project from a natural-language "
            "software requirement and automatically "
            "validate and repair it."
        )

    with right:

        st.markdown(
            "#### 📤 Re-check edited code"
        )

        st.write(
            "Upload a modified project and send it "
            "through the same validation and "
            "self-healing pipeline."
        )

    if st.session_state.project_directory:

        st.success(
            f"Current project: "
            f"{st.session_state.project_name}"
        )


# ============================================================
# PROJECT BUILDER
# ============================================================
# Planner + Blueprint + Builder are now ONE module.
# ============================================================

elif selected == "🏗️ Project Builder":

    st.subheader(
        "Project Builder"
    )

    st.caption(
        "Plan, refine, blueprint, approve and generate "
        "your project from one continuous conversation."
    )

    # ========================================================
    # PROJECT INPUT
    # ========================================================

    st.session_state.project_name = st.text_input(
        "Project name",
        value=st.session_state.project_name,
        placeholder="Inventory Management System",
    )

    description = st.text_area(
        "Project requirement",
        value=st.session_state.project_description,
        height=180,
        placeholder=(
            "Build an Inventory and Stock Management "
            "System with product management, stock "
            "tracking, low-stock alerts and dashboard..."
        ),
    )

    st.session_state.project_description = description

    # ========================================================
    # INITIAL PLAN
    # ========================================================

    if not st.session_state.project_plan:

        if st.button(
            "🧠 Generate Project Plan",
            type="primary",
            use_container_width=True,
        ):

            if not st.session_state.project_name.strip():

                st.warning(
                    "Please enter a project name."
                )

            elif not description.strip():

                st.warning(
                    "Please describe the project."
                )

            else:

                try:

                    reset_generated_project_state()

                    st.session_state.project_name = (
                        st.session_state.project_name.strip()
                    )

                    st.session_state.project_description = (
                        description
                    )

                    with st.spinner(
                        "Planning your project..."
                    ):

                        plan = generate_project_plan(
                            project_name=(
                                st.session_state.project_name
                            ),
                            project_description=(
                                description
                            ),
                        )

                    st.session_state.project_plan = plan

                    # ONE continuous conversation
                    st.session_state.project_chat_messages = [
                        {
                            "role": "assistant",
                            "content": (
                                "I've created the initial project "
                                "plan. You can now tell me anything "
                                "you want to add, remove, change or "
                                "improve before we create the blueprint."
                            ),
                        }
                    ]

                    st.success(
                        "✅ Initial project plan generated."
                    )

                    st.rerun()

                except Exception as error:

                    st.error(
                        f"Plan generation failed: {error}"
                    )

    # ========================================================
    # PLAN
    # ========================================================

    if st.session_state.project_plan:

        st.markdown(
            "### 🧠 Current Project Plan"
        )

        display_plan_summary(
            st.session_state.project_plan
        )

        with st.expander(
            "View detailed plan"
        ):

            display_detailed_plan(
                st.session_state.project_plan
            )

        # ====================================================
        # ONE CONTINUOUS CHAT
        # ====================================================

        st.markdown(
            "### 💬 Chat With Your Project Agent"
        )

        st.caption(
            "Use this same chat to refine the plan and "
            "blueprint. You can add, remove or change "
            "anything before approving the project."
        )

        for message in (
            st.session_state.project_chat_messages
        ):

            with st.chat_message(
                message["role"]
            ):

                st.markdown(
                    message["content"]
                )

        chat_placeholder = (
            "Example: Add authentication, "
            "admin dashboard and Excel export..."
        )

        user_message = st.chat_input(
            chat_placeholder,
            key="project_chat_input",
        )

        if user_message:

            st.session_state.project_chat_messages.append(
                {
                    "role": "user",
                    "content": user_message,
                }
            )

            try:

                with st.spinner(
                    "Updating your project..."
                ):

                    updated_plan = modify_project_plan(
                        current_plan=(
                            st.session_state.project_plan
                        ),
                        modification=user_message,
                    )

                    st.session_state.project_plan = (
                        updated_plan
                    )

                    # Any change means the current blueprint
                    # is no longer considered approved.
                    st.session_state.project_blueprint = None
                    st.session_state.blueprint_approved = False

                    # Existing generated output is no longer
                    # valid for the changed requirements.
                    st.session_state.generated_files = []
                    st.session_state.saved_files = []
                    st.session_state.zip_bytes = None
                    st.session_state.project_directory = None
                    st.session_state.recovery_result = None

                    st.session_state.project_chat_messages.append(
                        {
                            "role": "assistant",
                            "content": (
                                "Done! I've updated the project "
                                "plan based on your request. "
                                "Review the updated plan above, "
                                "or continue chatting if you want "
                                "more changes."
                            ),
                        }
                    )

                st.rerun()

            except Exception as error:

                st.session_state.project_chat_messages.append(
                    {
                        "role": "assistant",
                        "content": (
                            f"I couldn't update the project: "
                            f"{error}"
                        ),
                    }
                )

                st.rerun()

        # ====================================================
        # BLUEPRINT GENERATION
        # ====================================================

        if not st.session_state.project_blueprint:

            st.markdown(
                "### 🏗️ Ready for Blueprint?"
            )

            st.caption(
                "Continue using the chat until the "
                "requirements are correct. When ready, "
                "generate the blueprint."
            )

            if st.button(
                "🏗️ Generate Final Blueprint",
                type="primary",
                use_container_width=True,
            ):

                try:

                    with st.spinner(
                        "Building the final blueprint..."
                    ):

                        resources = retrieve_resources(
                            plan_to_resource_query(
                                st.session_state.project_plan
                            )
                        )

                        st.session_state.resources = (
                            resources
                        )

                        blueprint = (
                            generate_project_blueprint(
                                project_name=(
                                    st.session_state.project_name
                                ),
                                project_description=(
                                    st.session_state.project_description
                                ),
                                project_plan=(
                                    st.session_state.project_plan
                                ),
                                resources=resources,
                            )
                        )

                    st.session_state.project_blueprint = (
                        blueprint
                    )

                    st.session_state.blueprint_approved = (
                        False
                    )

                    st.session_state.project_chat_messages.append(
                        {
                            "role": "assistant",
                            "content": (
                                "I've generated the final "
                                "blueprint. Review it below. "
                                "You can continue using this "
                                "same chat if you want to make "
                                "any changes."
                            ),
                        }
                    )

                    st.success(
                        "✅ Final blueprint generated."
                    )

                    # Immediately show blueprint
                    st.rerun()

                except Exception as error:

                    st.error(
                        f"Blueprint generation failed: {error}"
                    )

        # ====================================================
        # BLUEPRINT
        # ====================================================

        if st.session_state.project_blueprint:

            st.markdown(
                "### 📋 Final Blueprint"
            )

            st.markdown(
                st.session_state.project_blueprint
            )

            st.divider()

            # =================================================
            # SAME CHAT CONTINUES
            # =================================================

            st.markdown(
                "### 💬 Continue With Your Project Agent"
            )

            st.caption(
                "You are still in the same conversation. "
                "Ask for any blueprint or feature changes "
                "before approving."
            )

            # The existing conversation is rendered here
            # again only because Streamlit reruns the page.
            # There is still ONE message list and ONE chat
            # input in the entire module.
            #
            # IMPORTANT:
            # We do NOT create another chat_input here.
            #
            # The chat input above remains the single
            # continuous input for the entire workflow.

            st.info(
                "💡 Use the chat above to request changes. "
                "Your existing conversation remains active."
            )

            # =================================================
            # APPROVAL
            # =================================================

            st.markdown(
                "### ✅ Blueprint Approval"
            )

            if st.session_state.blueprint_approved:

                st.success(
                    "✅ Blueprint approved."
                )

            else:

                col1, col2 = st.columns(2)

                with col1:

                    if st.button(
                        "✅ Approve Blueprint",
                        type="primary",
                        use_container_width=True,
                    ):

                        st.session_state.blueprint_approved = (
                            True
                        )

                        st.rerun()

                with col2:

                    if st.button(
                        "✏️ Keep Editing",
                        use_container_width=True,
                    ):

                        st.info(
                            "Continue using the chat above "
                            "to request changes."
                        )

            # =================================================
            # BUILD AFTER APPROVAL
            # =================================================

            if st.session_state.blueprint_approved:

                st.divider()

                st.markdown(
                    "### 🚀 Build Project"
                )

                st.caption(
                    "The blueprint is approved. "
                    "You can now generate the project files."
                )

                if not st.session_state.generated_files:

                    if st.button(
                        "🚀 Generate Project",
                        type="primary",
                        use_container_width=True,
                    ):

                        try:

                            with st.spinner(
                                "Generating and saving the project..."
                            ):

                                result = (
                                    generate_project_files(
                                        st.session_state.project_blueprint
                                    )
                                )

                                generated_files = (
                                    result["files"]
                                )

                                (
                                    saved_directory,
                                    saved_files,
                                ) = save_project_files(
                                    files=generated_files,
                                    project_name=(
                                        st.session_state.project_name.strip()
                                    ),
                                    workspace_directory="workspace",
                                )

                                st.session_state.project_directory = (
                                    saved_directory
                                )

                                st.session_state.generated_files = (
                                    generated_files
                                )

                                st.session_state.saved_files = (
                                    saved_files
                                )

                                create_project_zip(
                                    project_directory=saved_directory,
                                    output_directory="deliverables",
                                )

                                st.session_state.zip_bytes = (
                                    create_zip_bytes(
                                        project_directory=saved_directory
                                    )
                                )

                                st.session_state.recovery_result = (
                                    None
                                )

                            st.success(
                                "✅ Project generated and saved "
                                "to the workspace."
                            )

                            st.rerun()

                        except Exception as error:

                            st.error(
                                f"Source-code generation failed: "
                                f"{error}"
                            )

                else:

                    st.success(
                        "✅ Project has already been generated."
                    )

                # --------------------------------------------
                # DOWNLOAD
                # --------------------------------------------

                if st.session_state.zip_bytes:

                    safe_name = safe_project_name(
                        st.session_state.project_name
                    )

                    st.download_button(
                        "⬇️ Download generated project",
                        data=st.session_state.zip_bytes,
                        file_name=f"{safe_name}.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )


# ============================================================
# WORKSPACE
# ============================================================

elif selected == "📁 Workspace":

    st.subheader("Workspace")

    project_dir = (
        st.session_state.project_directory
    )

    if not project_dir:

        st.info(
            "No generated project is available yet. "
            "Build a project first."
        )

    else:

        project_path = Path(project_dir)

        st.caption(
            f"Project location: {project_path}"
        )

        files = [
            p
            for p in project_path.rglob("*")
            if (
                p.is_file()
                and "__pycache__" not in p.parts
            )
        ]

        st.write(
            f"**{len(files)} file(s)**"
        )

        if files:

            selected_file = st.selectbox(
                "Select a file",
                files,
                format_func=lambda p: str(
                    p.relative_to(project_path)
                ),
            )

            relative = selected_file.relative_to(
                project_path
            )

            st.markdown(
                f"### `{relative}`"
            )

            try:

                content = selected_file.read_text(
                    encoding="utf-8"
                )

                st.code(
                    content,
                    language=language_for_file(
                        str(selected_file)
                    ),
                )

            except UnicodeDecodeError:

                st.warning(
                    "This file is not a text file and "
                    "cannot be displayed here."
                )


# ============================================================
# SELF-HEALING
# ============================================================

elif selected == "🩺 Self-Healing":

    st.subheader(
        "Self-Healing & Recovery"
    )

    if not st.session_state.project_directory:

        st.info(
            "Generate a project first."
        )

    else:

        st.write(
            f"**Project:** "
            f"{st.session_state.project_name}"
        )

        st.write(
            f"**Files:** "
            f"{len(st.session_state.generated_files)}"
        )

        if (
            st.session_state.validation_status
            == "running"
        ):

            st.info(
                "Validation and recovery are running..."
            )

        if st.session_state.validation_error:

            st.error(
                st.session_state.validation_error
            )

        if not st.session_state.recovery_result:

            if st.button(
                "🧪 Run validation & self-healing",
                type="primary",
                use_container_width=True,
            ):

                st.session_state.validation_status = (
                    "running"
                )

                st.session_state.validation_error = None

                try:

                    with st.status(
                        "🧪 Running autonomous validation "
                        "and recovery...",
                        expanded=True,
                    ) as status_box:

                        st.write(
                            "🔎 Running project validation..."
                        )

                        result = run_with_self_healing(
                            project_directory=(
                                st.session_state.project_directory
                            ),
                            max_retries=3,
                        )

                        if not isinstance(
                            result,
                            dict,
                        ):

                            raise RuntimeError(
                                "Unexpected recovery result type: "
                                f"{type(result).__name__}"
                            )

                        st.session_state.recovery_result = (
                            result
                        )

                        st.session_state.validation_status = (
                            "complete"
                        )

                        repair_attempts = result.get(
                            "repair_attempts",
                            len(
                                history_by_type(
                                    result.get(
                                        "history",
                                        [],
                                    ),
                                    "repair",
                                )
                            ),
                        )

                        if (
                            result.get("success")
                            and repair_attempts > 0
                        ):

                            status_box.update(
                                label=(
                                    "✅ Recovery complete — "
                                    "project repaired successfully "
                                    f"after {repair_attempts} "
                                    "repair attempt"
                                    f"{'s' if repair_attempts != 1 else ''}."
                                ),
                                state="complete",
                                expanded=False,
                            )

                        elif (
                            result.get("success")
                            and repair_attempts == 0
                        ):

                            status_box.update(
                                label=(
                                    "✅ Project is already valid — "
                                    "no repair was required."
                                ),
                                state="complete",
                                expanded=False,
                            )

                        else:

                            status_box.update(
                                label=(
                                    "⚠️ Recovery finished — "
                                    "project still needs attention."
                                ),
                                state="error",
                                expanded=True,
                            )

                    add_recovery_history(
                        st.session_state.project_name,
                        result,
                        "Generated Project",
                    )

                except Exception as error:

                    st.session_state.validation_status = (
                        "error"
                    )

                    st.session_state.validation_error = (
                        str(error)
                    )

        if st.session_state.recovery_result:

            render_recovery_trace(
                st.session_state.recovery_result
            )


# ============================================================
# RE-CHECK EDITED PROJECT
# ============================================================

elif selected == "📤 Re-check Edited Project":

    st.subheader(
        "Re-check Edited Project"
    )

    st.caption(
        "Upload a modified project and send it through "
        "the same validation and self-healing workflow."
    )

    st.info(
        "ZIP is recommended for multi-file projects. "
        "A single .py file is also supported and will "
        "be treated as app.py."
    )

    uploaded_file = st.file_uploader(
        "Upload edited project",
        type=["zip", "py"],
        key="edited_project_uploader",
    )

    if uploaded_file is not None:

        if st.button(
            "📥 Load Edited Project",
            type="primary",
            use_container_width=True,
        ):

            try:

                reset_uploaded_state()

                project_path = save_uploaded_project(
                    uploaded_file
                )

                st.session_state.uploaded_project_path = (
                    str(project_path)
                )

                st.session_state.uploaded_project_name = (
                    project_path.name
                )

                st.success(
                    f"Uploaded project loaded: "
                    f"{project_path.name}"
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Could not load project: {error}"
                )

    if st.session_state.uploaded_project_path:

        project_path = Path(
            st.session_state.uploaded_project_path
        )

        st.markdown(
            f"### 📁 "
            f"{st.session_state.uploaded_project_name}"
        )

        st.caption(
            f"Project location: {project_path}"
        )

        files = [
            p
            for p in project_path.rglob("*")
            if (
                p.is_file()
                and "__pycache__" not in p.parts
            )
        ]

        st.write(
            f"Detected **{len(files)} file(s)**"
        )

        with st.expander(
            "View uploaded project files"
        ):

            for path in files:

                st.markdown(
                    f"**{path.relative_to(project_path)}**"
                )

        if not st.session_state.uploaded_recovery_result:

            if st.button(
                "🩺 Check for errors & self-heal",
                type="primary",
                use_container_width=True,
            ):

                st.session_state.uploaded_validation_status = (
                    "running"
                )

                st.session_state.uploaded_validation_error = (
                    None
                )

                try:

                    with st.status(
                        "🧪 Checking edited project...",
                        expanded=True,
                    ) as status_box:

                        st.write(
                            "🔎 Validating uploaded project..."
                        )

                        result = run_with_self_healing(
                            project_directory=str(
                                project_path
                            ),
                            max_retries=3,
                        )

                        if not isinstance(
                            result,
                            dict,
                        ):

                            raise RuntimeError(
                                "Unexpected recovery result type: "
                                f"{type(result).__name__}"
                            )

                        st.session_state.uploaded_recovery_result = (
                            result
                        )

                        st.session_state.uploaded_validation_status = (
                            "complete"
                        )

                        repair_attempts = result.get(
                            "repair_attempts",
                            len(
                                history_by_type(
                                    result.get(
                                        "history",
                                        [],
                                    ),
                                    "repair",
                                )
                            ),
                        )

                        if (
                            result.get("success")
                            and repair_attempts > 0
                        ):

                            status_box.update(
                                label=(
                                    "✅ Edited project recovered "
                                    "successfully after "
                                    f"{repair_attempts} "
                                    "repair attempt"
                                    f"{'s' if repair_attempts != 1 else ''}."
                                ),
                                state="complete",
                                expanded=False,
                            )

                        elif (
                            result.get("success")
                            and repair_attempts == 0
                        ):

                            status_box.update(
                                label=(
                                    "✅ Project is already valid — "
                                    "no repair was required."
                                ),
                                state="complete",
                                expanded=False,
                            )

                        else:

                            status_box.update(
                                label=(
                                    "⚠️ Recovery finished — "
                                    "project still needs attention."
                                ),
                                state="error",
                                expanded=True,
                            )

                    add_recovery_history(
                        st.session_state.uploaded_project_name,
                        result,
                        "Uploaded Edited Project",
                    )

                except Exception as error:

                    st.session_state.uploaded_validation_status = (
                        "error"
                    )

                    st.session_state.uploaded_validation_error = (
                        str(error)
                    )

        if st.session_state.uploaded_validation_error:

            st.error(
                st.session_state.uploaded_validation_error
            )

        if st.session_state.uploaded_recovery_result:

            render_recovery_trace(
                st.session_state.uploaded_recovery_result
            )

            # --------------------------------------------
            # DOWNLOAD REPAIRED PROJECT
            # --------------------------------------------

            repaired_zip = create_zip_bytes(
                project_directory=project_path
            )

            repaired_name = safe_project_name(
                st.session_state.uploaded_project_name
            )

            st.download_button(
                "⬇️ Download repaired project",
                data=repaired_zip,
                file_name=f"{repaired_name}_repaired.zip",
                mime="application/zip",
                use_container_width=True,
            )


# ============================================================
# RECOVERY HISTORY
# ============================================================

elif selected == "📜 Recovery History":

    st.subheader(
        "Recovery History"
    )

    if not st.session_state.recovery_history:

        st.info(
            "No recovery sessions have been recorded "
            "in this Streamlit session yet."
        )

    else:

        for index, item in enumerate(
            reversed(
                st.session_state.recovery_history
            ),
            start=1,
        ):

            if (
                item["success"]
                and item["repair_attempts"] > 0
            ):

                status = "✅ Recovered"

            elif (
                item["success"]
                and item["repair_attempts"] == 0
            ):

                status = "✅ Already valid"

            else:

                status = "⚠️ Needs attention"

            with st.expander(
                f"{status} — "
                f"{item['project_name']} "
                f"({item['source']})"
            ):

                st.write(
                    f"**Repair attempts:** "
                    f"{item['repair_attempts']}"
                )

                result = {
                    "success": item["success"],
                    "repair_attempts": item[
                        "repair_attempts"
                    ],
                    "history": item["history"],
                }

                render_recovery_trace(
                    result
                )