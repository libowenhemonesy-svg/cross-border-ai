"""知识库内可索引的 Markdown 文件。"""
from pathlib import Path


def markdown_files(vault: Path) -> list[Path]:
    root = vault.resolve()
    return sorted(
        path for path in vault.rglob("*.md")
        if path.is_file()
        and not path.is_symlink()
        and not any(part.startswith(".") for part in path.relative_to(vault).parts)
        and path.resolve().is_relative_to(root)
    )
