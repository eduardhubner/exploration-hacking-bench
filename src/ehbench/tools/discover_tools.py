from inspect_ai.tool import tool
from inspect_ai.model import get_model
from pathlib import Path

@tool
def list_files(folder_path: str):
    async def execute() -> str:
        """List all files available in your working directory.

        Call this first (with no arguments) before answering any question,
        to discover what context files are available to you.
        """
        folder = Path(folder_path)
        if not folder.exists():
            return "Error: folder not found"

        files = [f.name for f in folder.iterdir() if f.is_file()]
        return "\n".join(files)
    return execute


@tool
def read_file(folder_path: str):
    async def execute(filename: str) -> str:
        """Read the full contents of a file in your working directory.

        Call this for each file returned by list_files() to read its contents.

        Args:
            filename: Name of the file to read (as returned by list_files).
        """
        folder = Path(folder_path)
        if not folder.exists():
            return "Error: folder not found"

        file_path = folder / filename
        if not str(file_path.resolve()).startswith(str(folder.resolve())):
            return "Error: illegitimate file name"

        if not file_path.exists() or not file_path.is_file():
            return "Error: file does not exist"

        content = file_path.read_text()
        raw_name = get_model().name
        model_name = raw_name.split("/")[-1] if "/" in raw_name else raw_name
        return content.replace("{model_name}", model_name)



    
    return execute