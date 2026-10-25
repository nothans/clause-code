"""Configuration management for Clause Code."""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

API_KEY_ENV = "ANTHROPIC_API_KEY"


class ClauseConfig(BaseModel):
    """Configuration model for Clause Code.

    The API key is deliberately not part of this model: it lives in its own
    owner-only file (or the environment) and is never written to config.json.
    """

    default_model: str = Field(default="opus", pattern="^(opus|sonnet|haiku)$")
    festive_mode: bool = True
    project_folder: Optional[str] = None

    @field_validator("festive_mode", mode="before")
    @classmethod
    def validate_festive_mode(cls, v):
        """Validate and convert festive_mode to boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "y")
        return bool(v)


class ConfigManager:
    """Manages Clause Code configuration."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize config manager.

        Args:
            config_dir: Directory for config files. Defaults to ~/.clause-code
        """
        self.config_dir = config_dir or Path.home() / ".clause-code"
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config_file = self.config_dir / "config.json"
        self.api_key_file = self.config_dir / ".api_key"
        self._config: Optional[ClauseConfig] = None

    def load(self) -> ClauseConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                self._config = ClauseConfig(**json.load(f))
        else:
            self._config = ClauseConfig()

        return self._config

    def save(self, config: ClauseConfig) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
        """
        tmp_file = self.config_file.with_suffix(".json.tmp")
        with open(tmp_file, "w") as f:
            json.dump(config.model_dump(), f, indent=2)
        tmp_file.replace(self.config_file)

        self._config = config

    def get_api_key(self) -> Optional[str]:
        """Get the API key.

        The ANTHROPIC_API_KEY environment variable wins over the saved key, so a
        key set for one shell session is never written to disk.

        Returns:
            API key if available, None otherwise
        """
        env_key = os.getenv(API_KEY_ENV)
        if env_key:
            return env_key
        if self.api_key_file.exists():
            return self.api_key_file.read_text().strip() or None
        return None

    def set_api_key(self, api_key: str) -> None:
        """Save the API key to an owner-only file.

        Args:
            api_key: Anthropic API key
        """
        # Create the file with 0o600 up front so it is never readable by others,
        # even briefly; chmod covers a file left over from an older version.
        fd = os.open(self.api_key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(api_key)
        try:
            os.chmod(self.api_key_file, 0o600)
        except OSError:
            pass  # Windows has no POSIX permission bits

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
        config.project_folder = str(Path(folder).expanduser().resolve())
        self.save(config)

    def get_model(self) -> str:
        """Get configured model.

        Returns:
            Model name (opus, sonnet, or haiku)
        """
        return self.load().default_model

    def set_model(self, model: str) -> None:
        """Set default model.

        Args:
            model: Model name (opus, sonnet, or haiku)
        """
        config = self.load()
        config.default_model = model
        self.save(config)

    def is_festive_mode(self) -> bool:
        """Check if festive mode is enabled.

        Returns:
            True if festive mode is enabled
        """
        return self.load().festive_mode

    def set_festive_mode(self, enabled: bool) -> None:
        """Set festive mode.

        Args:
            enabled: Whether to enable festive mode
        """
        config = self.load()
        config.festive_mode = enabled
        self.save(config)
