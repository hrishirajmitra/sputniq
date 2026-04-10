import zipfile
from pathlib import Path


def _package_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(source_dir))


def create_complex_agent_app() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    source_dir = base_dir / "complex_agent_app"
    zip_path = base_dir / "complex_agent_app.zip"

    if not source_dir.exists():
        raise FileNotFoundError(f"Complex agent app directory not found: {source_dir}")

    _package_directory(source_dir, zip_path)
    print(f"Packaged complex agent app from {source_dir} into {zip_path}")


if __name__ == "__main__":
    create_complex_agent_app()
