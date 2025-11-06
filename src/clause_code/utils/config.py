"""Configuration management for Clause Code."""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ClauseConfig(BaseModel):
    """Configuration model for Clause Code."""

    api_key: Optional[str] = None
    default_model: str = Field(default="sonnet", pattern="^(sonnet|haiku|opus)$")
    festive_mode: bool = True
    project_folder: Optional[str] = None
    theme: str = "monokai"

    @field_validator('festive_mode', mode='before')
    @classmethod
    def validate_festive_mode(cls, v):
        """Validate and convert festive_mode to boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'y')
        return bool(v)


class ConfigManager:
    """Manages Clause Code configuration."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize config manager.

        Args:
            config_dir: Directory for config files. Defaults to ~/.clause-code
        """
        self.config_dir = config_dir or Path.home() / ".clause-code"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.api_key_file = self.config_dir / ".api_key"
        self._config: Optional[ClauseConfig] = None

    def load(self) -> ClauseConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                data = json.load(f)
                self._config = ClauseConfig(**data)
        else:
            self._config = ClauseConfig()

        # Load API key from separate secure file
        if self.api_key_file.exists():
            with open(self.api_key_file, "r") as f:
                self._config.api_key = f.read().strip()

        # Check environment variable as fallback
        if not self._config.api_key:
            self._config.api_key = os.getenv("ANTHROPIC_API_KEY")

        return self._config

    def save(self, config: ClauseConfig) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
        """
        # Save API key separately for security
        if config.api_key:
            with open(self.api_key_file, "w") as f:
                f.write(config.api_key)
            # Make API key file readable only by owner on Unix systems
            try:
                os.chmod(self.api_key_file, 0o600)
            except (OSError, AttributeError):
                pass  # Windows doesn't support chmod

        # Save config without API key
        config_dict = config.model_dump(exclude={"api_key"})
        with open(self.config_file, "w") as f:
            json.dump(config_dict, f, indent=2)

        self._config = config

    def get_api_key(self) -> Optional[str]:
        """Get API key from config or environment.

        Returns:
            API key if available, None otherwise
        """
        config = self.load()
        return config.api_key

    def set_api_key(self, api_key: str) -> None:
        """Set API key.

        Args:
            api_key: Anthropic API key
        """
        config = self.load()
        config.api_key = api_key
        self.save(config)

    def get_project_folder(self) -> Optional[Path]:
        """Get configured project folder.

        Returns:
            Path to project folder if set, None otherwise
        """
        config = self.load()
        if config.project_folder:
            return Path(config.project_folder)
        return None

    def set_project_folder(self, folder: str) -> None:
        """Set project folder.

        Args:
            folder: Path to project folder
        """
        config = self.load()
        # Expand user home directory and resolve to absolute path
        path = Path(folder).expanduser().resolve()
        config.project_folder = str(path)
        self.save(config)

    def get_model(self) -> str:
        """Get configured model.

        Returns:
            Model name (sonnet, haiku, or opus)
        """
        config = self.load()
        return config.default_model

    def set_model(self, model: str) -> None:
        """Set default model.

        Args:
            model: Model name (sonnet, haiku, or opus)
        """
        config = self.load()
        config.default_model = model
        self.save(config)

    def is_festive_mode(self) -> bool:
        """Check if festive mode is enabled.

        Returns:
            True if festive mode is enabled
        """
        config = self.load()
        return config.festive_mode

    def set_festive_mode(self, enabled: bool) -> None:
        """Set festive mode.

        Args:
            enabled: Whether to enable festive mode
        """
        config = self.load()
        config.festive_mode = enabled
        self.save(config)
