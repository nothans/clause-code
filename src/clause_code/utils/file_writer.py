"""File writing utilities for Clause Code."""

import re
from pathlib import Path
from typing import List, Tuple

from rich.console import Console


class FileExtractor:
    """Extract and write files from Claude responses."""

    def __init__(self, console: Console):
        """Initialize file extractor.
        
        Args:
            console: Rich console for output
        """
        self.console = console

    def extract_files(self, response: str) -> List[Tuple[str, str, str]]:
        """Extract file paths and content from response.
        
        Args:
            response: Claude's response text
            
        Returns:
            List of (filepath, content, language) tuples
        """
        files = []
        seen_files = set()
        
        # Pattern to match: **File: `path/to/file.ext`** followed by code block
        pattern = r'\*\*File:\s*`([^`]+)`\*\*\s*\n```(\w+)?\n(.*?)\n```'
        
        matches = re.finditer(pattern, response, re.DOTALL)
        
        for match in matches:
            filepath = match.group(1).strip()
            language = match.group(2) or 'text'
            content = match.group(3).strip()
            
            # Avoid duplicates
            if filepath not in seen_files:
                files.append((filepath, content, language))
                seen_files.add(filepath)
        
        return files

    def write_files(
        self,
        files: List[Tuple[str, str, str]],
        base_path: Path,
        overwrite: bool = True,
        safe_mode: bool = False
    ) -> List[str]:
        """Write extracted files to disk.

        Args:
            files: List of (filepath, content, language) tuples
            base_path: Base directory for file paths
            overwrite: Whether to overwrite existing files (default: True)
            safe_mode: If True, skip files that would escape base_path (default: False)

        Returns:
            List of created file paths
        """
        created_files = []

        for filepath, content, language in files:
            try:
                # Validate filepath
                if not filepath or filepath.strip() == "":
                    self.console.print("[yellow]⚠ Skipping empty filepath[/yellow]")
                    continue

                # Resolve full path
                full_path = (base_path / filepath).resolve()

                # Security check: ensure path is within base_path
                if safe_mode:
                    try:
                        full_path.relative_to(base_path.resolve())
                    except ValueError:
                        self.console.print(
                            f"[red]✗ Security: {filepath} attempts to escape base path[/red]"
                        )
                        continue

                # Check if file exists
                if full_path.exists() and not overwrite:
                    self.console.print(
                        f"[yellow]⚠ Skipped (exists): {filepath}[/yellow]"
                    )
                    continue

                # Create parent directories
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Validate content
                if content is None:
                    self.console.print(f"[yellow]⚠ Skipping {filepath}: No content[/yellow]")
                    continue

                # Write file
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                created_files.append(str(full_path))

                # Show appropriate message
                if full_path.exists():
                    action = "Updated" if overwrite else "Created"
                else:
                    action = "Created"

                self.console.print(f"[green]✓ {action}: {filepath}[/green]")

            except PermissionError:
                self.console.print(
                    f"[red]✗ Permission denied: {filepath}[/red]"
                )
            except OSError as e:
                self.console.print(
                    f"[red]✗ OS error creating {filepath}: {e}[/red]"
                )
            except Exception as e:
                self.console.print(
                    f"[red]✗ Error creating {filepath}: {e}[/red]"
                )

        return created_files
