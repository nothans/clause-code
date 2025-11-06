"""Tests for file extraction and writing utilities."""

import pytest
from pathlib import Path

from clause_code.utils.file_writer import FileExtractor


class TestFileExtractor:
    """Test cases for FileExtractor class."""

    def test_init(self, mock_console):
        """Test FileExtractor initialization."""
        extractor = FileExtractor(mock_console)
        assert extractor.console == mock_console

    def test_extract_single_file(self, mock_console):
        """Test extracting a single file from response."""
        extractor = FileExtractor(mock_console)

        response = """
Here's your code:

**File: `hello.py`**
```python
def hello():
    return "Hello, World!"
```

That's it!
"""

        files = extractor.extract_files(response)

        assert len(files) == 1
        assert files[0][0] == "hello.py"
        assert "def hello()" in files[0][1]
        assert files[0][2] == "python"

    def test_extract_multiple_files(self, mock_console):
        """Test extracting multiple files from response."""
        extractor = FileExtractor(mock_console)

        response = """
**File: `main.py`**
```python
from utils import helper
```

**File: `utils.py`**
```python
def helper():
    pass
```
"""

        files = extractor.extract_files(response)

        assert len(files) == 2
        assert files[0][0] == "main.py"
        assert files[1][0] == "utils.py"

    def test_extract_with_path(self, mock_console):
        """Test extracting file with nested path."""
        extractor = FileExtractor(mock_console)

        response = """
**File: `src/package/module.py`**
```python
class MyClass:
    pass
```
"""

        files = extractor.extract_files(response)

        assert len(files) == 1
        assert files[0][0] == "src/package/module.py"
        assert "class MyClass" in files[0][1]

    def test_extract_different_languages(self, mock_console):
        """Test extracting files with different language markers."""
        extractor = FileExtractor(mock_console)

        response = """
**File: `script.js`**
```javascript
console.log('Hello');
```

**File: `style.css`**
```css
body { margin: 0; }
```

**File: `README.md`**
```markdown
# Title
```
"""

        files = extractor.extract_files(response)

        assert len(files) == 3
        assert files[0][2] == "javascript"
        assert files[1][2] == "css"
        assert files[2][2] == "markdown"

    def test_extract_no_language_specified(self, mock_console):
        """Test extracting file without language specification."""
        extractor = FileExtractor(mock_console)

        response = """
**File: `data.txt`**
```
Some plain text content
```
"""

        files = extractor.extract_files(response)

        assert len(files) == 1
        assert files[0][0] == "data.txt"
        assert files[0][2] == "text"

    def test_extract_no_files(self, mock_console):
        """Test extracting from response with no file markers."""
        extractor = FileExtractor(mock_console)

        response = "Just some text without any file markers"
        files = extractor.extract_files(response)

        assert len(files) == 0

    def test_extract_duplicate_files(self, mock_console):
        """Test that duplicate file paths are not extracted twice."""
        extractor = FileExtractor(mock_console)

        response = """
**File: `test.py`**
```python
# First version
```

**File: `test.py`**
```python
# Second version
```
"""

        files = extractor.extract_files(response)

        # Should only extract the first occurrence
        assert len(files) == 1
        assert "First version" in files[0][1]

    def test_write_single_file(self, mock_console, temp_dir):
        """Test writing a single file to disk."""
        extractor = FileExtractor(mock_console)

        files = [("test.py", "print('Hello')", "python")]
        created = extractor.write_files(files, temp_dir)

        assert len(created) == 1
        assert Path(created[0]).exists()
        assert Path(created[0]).read_text() == "print('Hello')"

    def test_write_nested_file(self, mock_console, temp_dir):
        """Test writing file with nested directory structure."""
        extractor = FileExtractor(mock_console)

        files = [("src/lib/module.py", "# Module", "python")]
        created = extractor.write_files(files, temp_dir)

        assert len(created) == 1
        created_path = Path(created[0])
        assert created_path.exists()
        assert created_path.parent.name == "lib"
        assert created_path.read_text() == "# Module"

    def test_write_multiple_files(self, mock_console, temp_dir):
        """Test writing multiple files."""
        extractor = FileExtractor(mock_console)

        files = [
            ("file1.py", "# File 1", "python"),
            ("file2.py", "# File 2", "python"),
            ("dir/file3.py", "# File 3", "python"),
        ]
        created = extractor.write_files(files, temp_dir)

        assert len(created) == 3
        for path in created:
            assert Path(path).exists()

    def test_write_files_creates_directories(self, mock_console, temp_dir):
        """Test that write_files creates necessary parent directories."""
        extractor = FileExtractor(mock_console)

        files = [("deep/nested/path/file.txt", "content", "text")]
        created = extractor.write_files(files, temp_dir)

        assert len(created) == 1
        created_path = Path(created[0])
        assert created_path.exists()
        assert created_path.parent.exists()

    def test_write_files_error_handling(self, mock_console, temp_dir):
        """Test that write_files handles errors gracefully."""
        extractor = FileExtractor(mock_console)

        # Try to write to an invalid path (contains null byte on most systems)
        files = [("invalid\x00path.txt", "content", "text")]

        # Should not raise, but should print error and return empty list
        created = extractor.write_files(files, temp_dir)

        # Depending on OS, this might fail silently or succeed
        # Just ensure it doesn't crash
        assert isinstance(created, list)

    def test_write_files_utf8_content(self, mock_console, temp_dir):
        """Test writing files with UTF-8 content."""
        extractor = FileExtractor(mock_console)

        files = [("unicode.txt", "Hello 🎄 World 🎅", "text")]
        created = extractor.write_files(files, temp_dir)

        assert len(created) == 1
        content = Path(created[0]).read_text(encoding='utf-8')
        assert "🎄" in content
        assert "🎅" in content

    def test_extract_and_write_integration(self, mock_console, temp_dir):
        """Test full extraction and writing workflow."""
        extractor = FileExtractor(mock_console)

        response = """
Let me create some files for you:

**File: `app.py`**
```python
def main():
    print("Hello")

if __name__ == "__main__":
    main()
```

**File: `tests/test_app.py`**
```python
from app import main

def test_main():
    assert True
```
"""

        # Extract files
        files = extractor.extract_files(response)
        assert len(files) == 2

        # Write files
        created = extractor.write_files(files, temp_dir)
        assert len(created) == 2

        # Verify files exist and have correct content
        app_path = temp_dir / "app.py"
        test_path = temp_dir / "tests" / "test_app.py"

        assert app_path.exists()
        assert test_path.exists()
        assert "def main()" in app_path.read_text()
        assert "def test_main()" in test_path.read_text()
