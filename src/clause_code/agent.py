"""Claude agent integration using Anthropic SDK."""

import asyncio
from typing import AsyncGenerator, Optional

from anthropic import AsyncAnthropic
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .theme import FestiveTheme, GrinchTheme


class ClaudeAgent:
    """Main agent for interacting with Claude via Anthropic SDK."""

    # Latest Claude model IDs (as of October 2025)
    MODELS = {
        "sonnet": {
            "id": "claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "emoji": "⛷️",
            "description": "Best for coding and agentic tasks",
            "max_tokens": 64000,
        },
        "haiku": {
            "id": "claude-haiku-4-5-20251001",
            "name": "Claude Haiku 4.5",
            "emoji": "🦌",
            "description": "Fastest model with near-frontier intelligence",
            "max_tokens": 64000,
        },
        "opus": {
            "id": "claude-opus-4-1-20250805",
            "name": "Claude Opus 4.1",
            "emoji": "🎅",
            "description": "Most capable for complex reasoning",
            "max_tokens": 32000,
        },
    }

    def __init__(
        self,
        api_key: str,
        model: str = "sonnet",
        festive_mode: bool = True,
        console: Optional[Console] = None,
    ):
        """Initialize Claude agent.

        Args:
            api_key: Anthropic API key
            model: Model to use (sonnet, haiku, or opus)
            festive_mode: Whether to use festive theming
            console: Rich console for output
        """
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.festive_mode = festive_mode
        self.console = console or Console()
        self.conversation_history = []

        # Select theme based on mode
        self.theme = FestiveTheme if festive_mode else GrinchTheme

    def get_model_id(self) -> str:
        """Get the current model ID.

        Returns:
            Claude model ID string
        """
        return self.MODELS[self.model]["id"]

    def get_model_info(self) -> dict:
        """Get information about the current model.

        Returns:
            Dictionary with model information
        """
        return self.MODELS[self.model]

    async def chat(
        self, message: str, system_prompt: Optional[str] = None, project_folder: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Chat with Claude and stream the response.

        Args:
            message: User message
            system_prompt: Optional system prompt
            project_folder: Optional project folder for context

        Yields:
            Response text chunks
        """
        # Add user message to history
        self.conversation_history.append({"role": "user", "content": message})

        # Show thinking state
        thinking_msg = self.theme.get_thinking_state()
        self.console.print(f"\n{thinking_msg}", style="italic green")

        try:
            # Create streaming request
            model_id = self.get_model_id()
            max_tokens = self.MODELS[self.model]["max_tokens"]

            messages_to_send = self.conversation_history.copy()

            # Build system prompt
            base_system = """You are Clause Code, a festive AI coding assistant that brings holiday cheer
to development! You help developers write code, build projects, and solve problems with a touch of
Christmas spirit. You're powered by Claude and built by the Clause Code team.

When helping users build projects or write code, you should:
- Create complete, working files with proper structure
- Suggest file names and paths
- Write full implementations, not just snippets
- Include necessary imports, comments, and documentation
- Build projects step-by-step with clear explanations"""

            if project_folder:
                base_system += f"""

IMPORTANT: The user has set a project folder at: {project_folder}

When creating or editing files:
1. Use this as the base directory for all file paths
2. Create files directly in this folder structure
3. Suggest appropriate subdirectories (src/, tests/, etc.)
4. When you provide code, I will automatically save it to files for the user
5. Use clear section markers like "File: path/to/file.py" before code blocks
6. After providing code, confirm what files were created

Format your file creations like this:
**File: `path/to/file.py`**
```python
# Your code here
```

This helps me automatically save files to the project folder."""

            if system_prompt:
                base_system += f"\n\n{system_prompt}"

            # Prepare stream parameters
            stream_params = {
                "model": model_id,
                "messages": messages_to_send,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "system": base_system,
            }

            async with self.client.messages.stream(**stream_params) as stream:
                full_response = []
                async for text in stream.text_stream:
                    full_response.append(text)
                    yield text

                # Add assistant response to history
                full_text = "".join(full_response)
                self.conversation_history.append({"role": "assistant", "content": full_text})

        except Exception as e:
            error_msg = self.theme.get_error_message()
            self.console.print(f"\n{error_msg}", style="bold red")

            # Provide more specific error messages
            error_str = str(e)
            if "authentication" in error_str.lower() or "api key" in error_str.lower():
                self.console.print("🔑 API key issue. Please check your key with /setkey", style="yellow")
            elif "rate limit" in error_str.lower():
                self.console.print("⏱️ Rate limit reached. Please wait a moment and try again.", style="yellow")
            elif "timeout" in error_str.lower():
                self.console.print("⏱️ Request timed out. Please check your connection and try again.", style="yellow")
            elif "connection" in error_str.lower() or "network" in error_str.lower():
                self.console.print("🌐 Network issue. Please check your internet connection.", style="yellow")
            else:
                self.console.print(f"Error: {error_str}", style="red")

            yield ""

    async def generate_code(
        self, prompt: str, language: str = "python"
    ) -> tuple[str, str]:
        """Generate code based on a prompt.

        Args:
            prompt: Description of what code to generate
            language: Programming language

        Returns:
            Tuple of (code, explanation)
        """
        system_prompt = f"""You are an expert {language} programmer. Generate clean, 
well-documented code. Include comments explaining key parts. Focus on best practices 
and readability."""

        full_prompt = f"""Generate {language} code for the following request:

{prompt}

Please provide:
1. The complete, working code
2. A brief explanation of how it works"""

        # Show thinking state
        thinking_msg = self.theme.get_thinking_state()
        self.console.print(f"\n{thinking_msg}", style="italic green")

        try:
            model_id = self.get_model_id()
            response = await self.client.messages.create(
                model=model_id,
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=self.MODELS[self.model]["max_tokens"],
                temperature=0.2,
                system=system_prompt,
            )

            # Parse response
            content = response.content[0].text

            # Try to extract code and explanation
            # This is a simple heuristic - in practice, you might want more sophisticated parsing
            code = content
            explanation = ""

            return code, explanation

        except Exception as e:
            error_msg = self.theme.get_error_message()
            self.console.print(f"\n{error_msg}", style="bold red")

            # Provide more specific error messages
            error_str = str(e)
            if "authentication" in error_str.lower() or "api key" in error_str.lower():
                self.console.print("🔑 API key issue. Please check your key with /setkey", style="yellow")
            elif "rate limit" in error_str.lower():
                self.console.print("⏱️ Rate limit reached. Please wait a moment and try again.", style="yellow")
            elif "connection" in error_str.lower():
                self.console.print("🌐 Network issue. Please check your internet connection.", style="yellow")
            else:
                self.console.print(f"Error: {error_str}", style="red")

            return "", ""

    def render_code(self, code: str, language: str = "python", title: str = None) -> None:
        """Render code with syntax highlighting.

        Args:
            code: Code to render
            language: Programming language for syntax highlighting
            title: Optional title for the code panel
        """
        if not title:
            title = f"🎁 {language.title()} Code" if self.festive_mode else f"{language.title()} Code"

        syntax = Syntax(
            code,
            language,
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
            background_color="default",
        )

        panel = Panel(
            syntax,
            title=title,
            border_style="green" if self.festive_mode else "blue",
            padding=(1, 2),
        )

        self.console.print(panel)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []

    def set_model(self, model: str) -> None:
        """Set the model to use.

        Args:
            model: Model name (sonnet, haiku, or opus)
        """
        if model in self.MODELS:
            self.model = model
        else:
            raise ValueError(f"Unknown model: {model}")

    def set_festive_mode(self, enabled: bool) -> None:
        """Set festive mode.

        Args:
            enabled: Whether to enable festive mode
        """
        self.festive_mode = enabled
        self.theme = FestiveTheme if enabled else GrinchTheme
