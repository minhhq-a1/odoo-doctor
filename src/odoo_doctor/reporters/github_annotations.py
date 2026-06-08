from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic


def _escape_data(value: str) -> str:
    """Escape data for GitHub Actions workflow commands.

    See: https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#escaping-data
    """
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    """Escape property value for GitHub Actions workflow commands.

    See: https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#escaping-property-values
    """
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def render_github_annotations(diagnostics: list[Diagnostic], repo_root: Path) -> str:
    """Render diagnostics as GitHub Actions annotations.

    Format: ::{level} file={relpath},line={line},col={col},title={title}::{message}
    """
    level_map = {
        "error": "error",
        "warning": "warning",
        "info": "notice",
    }

    # Sort deterministically: tier, file_path, line
    sorted_diags = sorted(diagnostics, key=lambda d: (d.tier, d.file_path, d.line))

    lines = []
    for d in sorted_diags:
        level = level_map.get(d.severity, "notice")

        # Relativize path
        try:
            rel_path = str(Path(d.file_path).resolve().relative_to(repo_root.resolve()))
        except ValueError:
            rel_path = Path(d.file_path).name

        title = _escape_property(d.title)
        message = _escape_data(d.message)

        line_str = f"::{level} file={rel_path},line={d.line},col={d.column},title={title}::{message}"
        lines.append(line_str)

    return "\n".join(lines) + ("\n" if lines else "")
