import streamlit as st
from pathlib import Path
import re
from src.agents.planner import (
    generate_project_plan,
    modify_project_plan,
)

from src.rag.resource_retriever import (
    retrieve_resources,
)

from src.agents.blueprint import (
    generate_project_blueprint,
)

from src.generators.code_generator import (
    generate_project_files,
)

from src.generators.project_saver import (
    save_project_files,
    create_project_zip,
    create_zip_bytes,
)

from src.recovery.recovery_manager import (
    run_with_self_healing,
)




# --------------------------------------------------
# Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="Self-Healing AI Agent",
    page_icon="🤖",
    layout="wide",
)


# --------------------------------------------------
# Session state initialization
# --------------------------------------------------

default_values = {
    "messages": [],
    "project_name": "",
    "project_description": "",
    "project_plan": None,
    "show_detailed_plan": False,
    "show_modify": False,
    "plan_approved": False,
    "resources": [],
    "resources_confirmed": False,
    "project_blueprint": None,
    "blueprint_approved": False,
    "generated_files": [],
    "zip_bytes": None,
    "recovery_result": None,
    "project_directory": None,
    "saved_files": [],
}

for key, value in default_values.items():
    if key not in st.session_state:
        st.session_state[key] = value


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def reset_project():
    """
    Reset the complete project workflow.
    """

    for key, value in default_values.items():
        st.session_state[key] = value

    st.rerun()


def display_plan_summary(plan):
    """
    Display the short project plan summary.
    """

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
    """
    Display the detailed plan.
    """

    if isinstance(plan, dict):
        detailed_plan = plan.get(
            "detailed_plan",
            "No detailed plan available.",
        )

        st.markdown(detailed_plan)

    else:
        st.markdown(str(plan))

def get_safe_project_name(project_name):
    """
    Convert a project name into a safe folder name.
    """

    safe_name = re.sub(
        r"[^a-zA-Z0-9_]+",
        "_",
        project_name.lower(),
    ).strip("_")

    return safe_name or "generated_project"


# --------------------------------------------------
# Sidebar
# --------------------------------------------------

with st.sidebar:
    st.header("⚙️ Project Settings")

    st.session_state.project_name = st.text_input(
        "Project Name",
        value=st.session_state.project_name,
        placeholder="Example: Trip Planner",
    )

    st.divider()

    st.write("### Workflow")

    st.write("1. Describe your application")
    st.write("2. Review the project plan")
    st.write("3. Confirm useful resources")
    st.write("4. Review the final blueprint")
    st.write("5. Generate source code")
    st.write("6. Download the project")

    st.divider()

    if st.button("🔄 Reset Project"):
        reset_project()


# --------------------------------------------------
# Main heading
# --------------------------------------------------

st.title("🤖 Self-Healing and Recovery Autonomous AI Agent")

st.caption(
    "Describe an application and let the AI plan, design, "
    "and generate the project step by step."
)


# --------------------------------------------------
# Display previous chat messages
# --------------------------------------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# --------------------------------------------------
# Chat input
# --------------------------------------------------

user_prompt = st.chat_input(
    "Describe the application you want me to build..."
)


if user_prompt:

    if not st.session_state.project_name or not st.session_state.project_name.strip():

        st.error(
            "Please enter a project name in the sidebar."
        )

    else:

        # Save the user's message
        st.session_state.messages.append(
            {
                "role": "user",
                "content": user_prompt,
            }
        )

        st.session_state.project_description = user_prompt

        # Reset the previous workflow
        st.session_state.project_plan = None
        st.session_state.show_detailed_plan = False
        st.session_state.show_modify = False
        st.session_state.plan_approved = False
        st.session_state.resources = []
        st.session_state.resources_confirmed = False
        st.session_state.project_blueprint = None
        st.session_state.blueprint_approved = False
        st.session_state.generated_files = []
        st.session_state.zip_bytes = None

        try:

            with st.spinner("Creating your project plan..."):

                plan = generate_project_plan(
                    project_name=(
                        st.session_state.project_name.strip()
                    ),
                    project_description=user_prompt,
                )

            # Save the generated plan
            st.session_state.project_plan = plan

            # Save assistant response permanently
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "I created an initial project plan. "
                        "Please review it below."
                    ),
                }
            )

            st.rerun()

        except Exception as error:

            # Save the error permanently so it does not disappear
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "I could not generate the project plan.\n\n"
                        f"**Error:** `{error}`"
                    ),
                }
            )

            st.rerun()


# --------------------------------------------------
# Project plan review
# --------------------------------------------------

if st.session_state.project_plan:

    with st.chat_message("assistant"):

        st.subheader("📋 Proposed Project Plan")

        display_plan_summary(
            st.session_state.project_plan
        )

        if st.button(
            "📖 Show Detailed Plan"
            if not st.session_state.show_detailed_plan
            else "📕 Hide Detailed Plan"
        ):
            st.session_state.show_detailed_plan = (
                not st.session_state.show_detailed_plan
            )
            st.rerun()

        if st.session_state.show_detailed_plan:

            st.markdown("### Detailed Plan")

            display_detailed_plan(
                st.session_state.project_plan
            )

        st.divider()

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "✅ Approve Plan",
                use_container_width=True,
            ):

                st.session_state.plan_approved = True
                st.session_state.show_modify = False

                with st.spinner(
                    "Retrieving useful resources..."
                ):

                    try:
                        st.session_state.resources = (
                            retrieve_resources(
                                st.session_state.project_plan
                            )
                        )

                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    "The project plan has been approved. "
                                    "I retrieved some useful resources "
                                    "for the next step."
                                ),
                            }
                        )

                        st.success(
                            "Plan approved and resources retrieved."
                        )

                    except Exception as error:
                        st.error(
                            f"Resource retrieval failed: {error}"
                        )

                st.rerun()

        with col2:

            if st.button(
                "✏️ Modify Plan",
                use_container_width=True,
            ):

                st.session_state.show_modify = True
                st.rerun()


# --------------------------------------------------
# Modify project plan
# --------------------------------------------------

if st.session_state.show_modify:

    with st.chat_message("assistant"):

        st.subheader("✏️ Modify Project Plan")

        modification = st.text_area(
            "What would you like to change?",
            placeholder=(
                "Example: Add user authentication, "
                "an admin dashboard, and email notifications."
            ),
            height=120,
        )

        if st.button(
            "Apply Modification",
            use_container_width=True,
        ):

            if not modification.strip():

                st.warning(
                    "Please enter a modification first."
                )

            else:

                with st.spinner(
                    "Updating your project plan..."
                ):

                    try:
                        updated_plan = modify_project_plan(
                            current_plan=(
                                st.session_state.project_plan
                            ),
                            modification=modification,
                        )

                        st.session_state.project_plan = (
                            updated_plan
                        )

                        st.session_state.plan_approved = False
                        st.session_state.resources = []
                        st.session_state.resources_confirmed = False
                        st.session_state.project_blueprint = None
                        st.session_state.blueprint_approved = False
                        st.session_state.generated_files = []
                        st.session_state.zip_bytes = None
                        st.session_state.show_modify = False

                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    "I updated the project plan "
                                    "according to your instructions."
                                ),
                            }
                        )

                        st.success(
                            "Project plan updated successfully."
                        )

                        st.rerun()

                    except Exception as error:

                        st.error(
                            f"Plan modification failed: {error}"
                        )


# --------------------------------------------------
# Resource review
# --------------------------------------------------

if st.session_state.plan_approved:

    with st.chat_message("assistant"):

        st.subheader("📚 Retrieved Resources")

        if not st.session_state.resources:

            st.info(
                "No matching resources were found. "
                "You can add resources manually."
            )

        for index, resource in enumerate(
            st.session_state.resources
        ):

            st.markdown(
                f"### {index + 1}. {resource['title']}"
            )

            st.write(
                resource.get(
                    "description",
                    "No description available.",
                )
            )

            st.markdown(
                f"[Open Resource]({resource['url']})"
            )

            if st.button(
                f"Remove {resource['title']}",
                key=f"remove_resource_{index}",
            ):

                st.session_state.resources.pop(index)
                st.rerun()

        st.divider()

        st.subheader("➕ Add a Resource")

        new_title = st.text_input(
            "Resource Title",
            key="new_resource_title",
        )

        new_url = st.text_input(
            "Resource URL",
            key="new_resource_url",
        )

        new_description = st.text_area(
            "Resource Description",
            key="new_resource_description",
        )

        if st.button(
            "Add Resource",
            use_container_width=True,
        ):

            if not new_title.strip() or not new_url.strip():

                st.warning(
                    "Please enter both a title and URL."
                )

            else:

                st.session_state.resources.append(
                    {
                        "title": new_title,
                        "description": new_description,
                        "url": new_url,
                        "keywords": [],
                    }
                )

                st.success("Resource added.")
                st.rerun()

        st.divider()

        if st.button(
            "✅ Confirm Resources",
            use_container_width=True,
        ):

            st.session_state.resources_confirmed = True

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "The resources have been confirmed. "
                        "The next step is generating the "
                        "final project blueprint."
                    ),
                }
            )

            st.rerun()


# --------------------------------------------------
# Generate final blueprint
# --------------------------------------------------

if st.session_state.resources_confirmed:

    with st.chat_message("assistant"):

        st.subheader("🏗️ Final Project Blueprint")

        st.write(
            "Your plan and resources are confirmed. "
            "Generate the final blueprint before creating source code."
        )

        if st.button(
            "Generate Final Blueprint",
            use_container_width=True,
        ):

            with st.spinner(
                "Generating the final project blueprint..."
            ):

                try:

                    blueprint = generate_project_blueprint(
                        project_name=(
                            st.session_state.project_name
                        ),
                        project_description=(
                            st.session_state.project_description
                        ),
                        project_plan=(
                            st.session_state.project_plan
                        ),
                        resources=(
                            st.session_state.resources
                        ),
                    )

                    st.session_state.project_blueprint = (
                        blueprint
                    )

                    st.success(
                        "Final project blueprint generated."
                    )

                    st.rerun()

                except Exception as error:

                    st.error(
                        f"Blueprint generation failed: {error}"
                    )


# --------------------------------------------------
# Blueprint approval
# --------------------------------------------------

if st.session_state.project_blueprint:

    with st.chat_message("assistant"):

        st.subheader("🏗️ Review Final Blueprint")

        st.markdown(
            st.session_state.project_blueprint
        )

        st.info(
            "Review the blueprint carefully before approving it."
        )

        if st.button(
            "✅ Approve Blueprint",
            use_container_width=True,
        ):

            st.session_state.blueprint_approved = True

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "The blueprint has been approved. "
                        "The source code can now be generated."
                    ),
                }
            )

            st.success(
                "Blueprint approved."
            )

            st.rerun()


# --------------------------------------------------
# Source-code generation
# --------------------------------------------------

# --------------------------------------------------
# Source-code generation
# --------------------------------------------------

if st.session_state.blueprint_approved:

    with st.chat_message("assistant"):

        st.subheader("💻 Source-Code Generation")

        st.write(
            "The blueprint is approved. "
            "You can now generate the project source code."
        )

        if st.button(
            "🚀 Generate Source Code",
            use_container_width=True,
        ):

            try:

                with st.spinner(
                    "Generating project source code..."
                ):

                    result = generate_project_files(
                        st.session_state.project_blueprint
                    )

                    generated_files = result["files"]

                    project_name = (
                        st.session_state.project_name
                    )

                    safe_project_name = (
                        get_safe_project_name(
                            project_name
                        )
                    )

                    project_directory = (
                        Path("workspace")
                        / safe_project_name
                    )

                    # Save the generated files as
                    # normal files inside workspace
                    saved_directory, saved_files = (
                        save_project_files(
                            files=generated_files,
                            project_name=project_name,
                            workspace_directory="workspace",
                        )
                    )

                    # Save the folder path
                    st.session_state.project_directory = (
                        saved_directory
                    )

                    # Save generated file information
                    st.session_state.generated_files = (
                        generated_files
                    )

                    # Create optional ZIP file
                    create_project_zip(
                        project_directory=saved_directory,
                        output_directory="deliverables",
                    )

                    # Create ZIP bytes for download
                    st.session_state.zip_bytes = (
                        create_zip_bytes(
                            project_directory=saved_directory
                        )
                    )

                    # Clear any old recovery result
                    st.session_state.recovery_result = None

                st.success(
                    "Source code generated and saved "
                    "as normal files inside the workspace folder."
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Source-code generation failed: {error}"
                )


# --------------------------------------------------
# Display generated files
# --------------------------------------------------

if st.session_state.generated_files:

    with st.chat_message("assistant"):

        st.subheader("📁 Generated Project Files")

        st.write(
            f"{len(st.session_state.generated_files)} "
            "files were generated."
        )

        for file in st.session_state.generated_files:

            st.markdown(
                f"### `{file['path']}`"
            )

            language = "text"

            if file["path"].endswith(".py"):
                language = "python"

            elif file["path"].endswith(".js"):
                language = "javascript"

            elif file["path"].endswith(".jsx"):
                language = "javascript"

            elif file["path"].endswith(".html"):
                language = "html"

            elif file["path"].endswith(".css"):
                language = "css"

            elif file["path"].endswith(".json"):
                language = "json"

            st.code(
                file["content"],
                language=language,
            )


# --------------------------------------------------
# Automatic testing and self-healing
# --------------------------------------------------

# --------------------------------------------------
# Automatic testing and self-healing
# --------------------------------------------------

if st.session_state.generated_files:

    with st.chat_message("assistant"):

        st.subheader(
            "🧪 Automatic Testing and Self-Healing"
        )

        st.write(
            "The project files have been generated. "
            "The agent can now run checks, detect errors, "
            "and attempt automatic repairs."
        )

        if st.session_state.get("project_directory"):

            st.info(
                "Project folder: "
                + str(
                    Path(
                        st.session_state.project_directory
                    ).resolve()
                )
            )

        if st.button(
            "▶️ Run Project Checks",
            use_container_width=True,
        ):

            project_directory = (
                st.session_state.get(
                    "project_directory"
                )
            )

            if not project_directory:

                st.error(
                    "Project directory was not found. "
                    "Please generate the source code again."
                )

            else:

                with st.spinner(
                    "Running the project and checking for errors..."
                ):

                    try:

                        recovery_result = (
                            run_with_self_healing(
                                project_directory=(
                                    project_directory
                                ),
                                max_retries=3,
                            )
                        )

                        st.session_state.recovery_result = (
                            recovery_result
                        )

                        st.rerun()

                    except Exception as error:

                        st.error(
                            f"Execution failed: {error}"
                        )


# --------------------------------------------------
# Display recovery report
# --------------------------------------------------

if st.session_state.get("recovery_result"):

    recovery_result = (
        st.session_state.recovery_result
    )

    with st.chat_message("assistant"):

        st.subheader("🔍 Recovery Report")

        if recovery_result["success"]:

            st.success(
                "The project passed all automatic checks."
            )

        else:

            st.error(
                "The project could not pass all checks."
            )

        st.write(
            f"Validation attempts performed: "
            f"{recovery_result['attempts']}"
        )

        history = recovery_result.get(
            "history",
            [],
        )

        repair_count = sum(
            1
            for item in history
            if item.get("type") == "repair"
        )

        st.write(
            f"Automatic repairs performed: "
            f"{repair_count}"
        )

        if repair_count == 0:

            st.info(
                "No repair was required because the "
                "project passed its first validation."
            )

        for item in history:

            item_type = item.get("type")

            if item_type == "validation":

                result = item.get(
                    "result",
                    {},
                )

                attempt_number = item.get(
                    "attempt",
                    "?",
                )

                if result.get("success"):

                    st.success(
                        f"Attempt {attempt_number}: "
                        "Validation passed"
                    )

                else:

                    st.error(
                        f"Attempt {attempt_number}: "
                        "Validation failed"
                    )

                    st.code(
                        result.get(
                            "summary",
                            "No error details available.",
                        )
                    )

            elif item_type == "repair":

                repair_result = item.get(
                    "result",
                    {},
                )

                st.info(
                    "🔧 Automatic repair performed"
                )

                st.write(
                    repair_result.get(
                        "explanation",
                        "The agent attempted to repair the project.",
                    )
                )


# --------------------------------------------------
# Download ZIP
# --------------------------------------------------

if st.session_state.zip_bytes:

    with st.chat_message("assistant"):

        st.subheader("📦 Project Files and ZIP Download")

        project_name = st.session_state.get(
            "project_name",
            "generated_project",
        )

        if st.session_state.get("project_directory"):

            folder_path = Path(
                st.session_state.project_directory
            ).resolve()

            st.success(
                "The project has been saved as normal files."
            )

            st.write("Project folder:")

            st.code(str(folder_path))

        st.write(
            "The ZIP file is optional and is provided "
            "only for convenient downloading."
        )

        safe_project_name = (
            get_safe_project_name(project_name)
        )

        st.download_button(
            label=f"⬇️ Download {project_name} ZIP",
            data=st.session_state.zip_bytes,
            file_name=f"{safe_project_name}.zip",
            mime="application/zip",
            use_container_width=True,
        )