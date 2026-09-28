from pathlib import Path
import io
import zipfile


def save_project_files(
    files,
    project_name,
    workspace_directory="workspace",
):
    """
    Save generated files as normal files inside workspace.
    """

    safe_project_name = (
        project_name
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )

    project_directory = (
        Path(workspace_directory)
        / safe_project_name
    )

    project_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_files = []

    for file in files:

        relative_path = Path(
            file["path"]
        )

        file_path = (
            project_directory
            / relative_path
        )

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_path.write_text(
            file["content"],
            encoding="utf-8",
        )

        saved_files.append(
            str(file_path)
        )

    return str(project_directory), saved_files


def create_project_zip(
    project_directory,
    output_directory="deliverables",
):
    """
    Create an optional ZIP file from the saved folder.
    """

    project_directory = Path(
        project_directory
    )

    output_directory = Path(
        output_directory
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    zip_path = (
        output_directory
        / f"{project_directory.name}.zip"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zip_file:

        for file_path in project_directory.rglob("*"):

            if file_path.is_file():

                archive_name = (
                    project_directory.name
                    / file_path.relative_to(
                        project_directory
                    )
                )

                zip_file.write(
                    file_path,
                    archive_name,
                )

    return str(zip_path)


def create_zip_bytes(
    project_directory,
):
    """
    Create ZIP bytes for Streamlit download.
    """

    project_directory = Path(
        project_directory
    )

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zip_file:

        for file_path in project_directory.rglob("*"):

            if file_path.is_file():

                archive_name = (
                    project_directory.name
                    / file_path.relative_to(
                        project_directory
                    )
                )

                zip_file.write(
                    file_path,
                    archive_name,
                )

    zip_buffer.seek(0)

    return zip_buffer.getvalue()