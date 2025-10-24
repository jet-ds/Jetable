"""Claude Code CLI adapter using stream-JSON protocol."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from app.core.terminal_ui import ui
from app.models.messages import Message

from ..base import BaseCLI, CLIType


def _image_to_dict(image: Any) -> Dict[str, Any]:
    if isinstance(image, dict):
        return image
    data: Dict[str, Any] = {}
    for key in ("name", "path", "base64_data", "mime_type"):
        data[key] = getattr(image, key, None)
    return data


def _strip_data_url(data: str) -> str:
    if "," in data and data.strip().startswith("data:"):
        return data.split(",", 1)[1]
    return data


class ClaudeCodeCLI(BaseCLI):
    """Claude Code CLI implementation via subprocess stream JSON."""

    def __init__(self):
        super().__init__(CLIType.CLAUDE)
        self._session_store: Dict[str, str] = {}

    async def check_availability(self) -> Dict[str, Any]:
        """Verify Claude CLI exists and responds."""
        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                msg = stderr.decode().strip() or stdout.decode().strip()
                return {
                    "available": False,
                    "configured": False,
                    "error": f"Claude CLI unavailable: {msg}",
                }
            return {
                "available": True,
                "configured": True,
                "mode": "CLI",
                "models": self.get_supported_models(),
                "default_models": [
                    "claude-sonnet-4-5-20250929",
                    "claude-opus-4-1-20250805",
                    "claude-haiku-4-5-20251001",
                ],
            }
        except FileNotFoundError:
            return {
                "available": False,
                "configured": False,
                "error": (
                    "Claude CLI not found. Install it with "
                    "`npm install -g @anthropic-ai/claude-code` and run `claude login`."
                ),
            }
        except Exception as exc:  # pragma: no cover
            return {
                "available": False,
                "configured": False,
                "error": f"Failed to check Claude CLI: {exc}",
            }

    async def execute_with_streaming(
        self,
        instruction: str,
        project_path: str,
        session_id: Optional[str] = None,
        log_callback: Optional[Callable[[str], Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        is_initial_prompt: bool = False,
    ) -> AsyncGenerator[Message, None]:
        """Run Claude CLI with stream-JSON interface."""

        project_repo_path = Path(project_path).resolve()
        if not project_repo_path.exists():
            raise FileNotFoundError(f"Project path not found: {project_repo_path}")

        cli_model = self._get_cli_model_name(model) or "claude-sonnet-4-5-20250929"
        ctx_instruction = self._augment_instruction(
            instruction, project_repo_path, is_initial_prompt
        )

        content_blocks, attachment_meta = self._build_content_blocks(
            ctx_instruction, images or [], project_repo_path
        )

        user_message = {
            "type": "user",
            "message": {
                "role": "user",
                "content": content_blocks,
            },
        }

        settings_file = self._write_temp_settings(project_repo_path)
        allowed_tools, disallowed_tools = self._tool_configuration(is_initial_prompt)

        cmd = [
            "claude",
            "--print",
            "--output-format=stream-json",
            "--input-format=stream-json",
            "--include-partial-messages",
            "--verbose",
            "--permission-mode",
            "bypassPermissions",
            "--model",
            cli_model,
        ]

        if settings_file:
            cmd.extend(["--settings", str(settings_file)])

        if allowed_tools:
            cmd.append("--allowed-tools")
            cmd.extend(allowed_tools)
        if disallowed_tools:
            cmd.append("--disallowed-tools")
            cmd.extend(disallowed_tools)

        existing_session = await self.get_session_id(project_repo_path.name)
        if existing_session and not is_initial_prompt:
            cmd.extend(["--resume", existing_session])

        ui.info("Starting Claude CLI process", "Claude CLI")
        ui.debug(f"Executing command: {' '.join(shlex.quote(part) for part in cmd)}", "Claude CLI")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_repo_path),
        )

        stderr_lines: List[str] = []
        stderr_task = asyncio.create_task(
            self._drain_stream(process.stderr, stderr_lines)
        )

        try:
            if process.stdin is None:
                raise RuntimeError("Claude CLI stdin unavailable")
            payload = json.dumps(user_message) + "\n"
            process.stdin.write(payload.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            ui.debug("Sent initial instruction to Claude CLI", "Claude CLI")
        except Exception as exc:
            process.kill()
            raise RuntimeError(f"Failed to send message to Claude CLI: {exc}") from exc

        assistant_buffer = ""
        turn_id = None
        result_emitted = False

        try:
            async for line in self._iter_stdout_lines(process.stdout):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    ui.debug(f"Non-JSON output: {line}", "Claude CLI")
                    continue

                msg_type = payload.get("type")

                if msg_type == "system":
                    subtype = payload.get("subtype")
                    session_identifier = payload.get("session_id")
                    if session_identifier:
                        await self.set_session_id(project_repo_path.name, session_identifier)
                    meta = {
                        "cli_type": self.cli_type.value,
                        "hidden_from_ui": True,
                        "event_type": subtype or "system",
                        "session_id": session_identifier,
                        "attachments": attachment_meta,
                    }
                    yield Message(
                        id=str(uuid.uuid4()),
                        project_id=str(project_repo_path),
                        role="system",
                        message_type="system",
                        content=f"Claude CLI initialized (Model: {cli_model})",
                        metadata_json=meta,
                        session_id=session_id,
                        created_at=datetime.utcnow(),
                    )

                elif msg_type == "stream_event":
                    event = payload.get("event", {})
                    event_type = event.get("type")
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        text = delta.get("text")
                        if text:
                            assistant_buffer += text
                    elif event_type == "tool_use":
                        summary = self._create_tool_summary(
                            event.get("name") or "tool",
                            event.get("input", {}),
                        )
                        yield Message(
                            id=str(uuid.uuid4()),
                            project_id=str(project_repo_path),
                            role="assistant",
                            message_type="tool_use",
                            content=summary,
                            metadata_json={
                                "cli_type": self.cli_type.value,
                                "tool_name": event.get("name"),
                                "original_event": event,
                            },
                            session_id=session_id,
                            created_at=datetime.utcnow(),
                        )
                    elif event_type == "tool_result":
                        content = event.get("content")
                        summary = self._create_tool_summary(
                            event.get("name") or "tool_result",
                            {"output": content},
                        )
                        yield Message(
                            id=str(uuid.uuid4()),
                            project_id=str(project_repo_path),
                            role="system",
                            message_type="tool_result",
                            content=summary,
                            metadata_json={
                                "cli_type": self.cli_type.value,
                                "hidden_from_ui": True,
                                "original_event": event,
                            },
                            session_id=session_id,
                            created_at=datetime.utcnow(),
                        )
                    elif event_type == "message_start":
                        turn_id = event.get("message", {}).get("id")

                elif msg_type == "assistant":
                    message = payload.get("message", {})
                    content = message.get("content", [])
                    text = self._extract_text_from_blocks(content) or assistant_buffer
                    if text:
                        yield Message(
                            id=str(uuid.uuid4()),
                            project_id=str(project_repo_path),
                            role="assistant",
                            message_type="chat",
                            content=text.strip(),
                            metadata_json={
                                "cli_type": self.cli_type.value,
                                "turn_id": turn_id,
                                "attachments": attachment_meta,
                            },
                            session_id=session_id,
                            created_at=datetime.utcnow(),
                        )
                    assistant_buffer = ""

                elif msg_type == "result":
                    result_emitted = True
                    is_error = payload.get("is_error", False)
                    meta = {
                        "cli_type": self.cli_type.value,
                        "event_type": "result",
                        "is_error": is_error,
                        "duration_ms": payload.get("duration_ms"),
                        "num_turns": payload.get("num_turns"),
                        "session_id": payload.get("session_id"),
                        "hidden_from_ui": True,
                    }
                    yield Message(
                        id=str(uuid.uuid4()),
                        project_id=str(project_repo_path),
                        role="system",
                        message_type="result",
                        content=payload.get("result", ""),
                        metadata_json=meta,
                        session_id=session_id,
                        created_at=datetime.utcnow(),
                    )

        finally:
            await process.wait()
            await stderr_task
            if settings_file and settings_file.exists():
                try:
                    settings_file.unlink()
                except Exception:
                    pass

        if process.returncode not in (0, None):
            stderr_text = "\n".join(stderr_lines)
            raise RuntimeError(
                f"Claude CLI exited with code {process.returncode}: {stderr_text}"
            )

        if not result_emitted:
            ui.warning("Claude CLI session ended without result event", "Claude CLI")

    async def _iter_stdout_lines(self, stream: asyncio.StreamReader):
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors="ignore").strip()
            if text:
                yield text

    async def _drain_stream(
        self, stream: asyncio.StreamReader, bucket: List[str]
    ) -> None:
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode(errors="ignore").strip()
                if decoded:
                    bucket.append(decoded)
        except Exception:
            pass

    def _augment_instruction(
        self, instruction: str, project_repo_path: Path, is_initial_prompt: bool
    ) -> str:
        if not is_initial_prompt:
            return instruction

        entries = []
        try:
            for item in sorted(project_repo_path.iterdir()):
                if item.name.startswith(".") and item.name not in {".env"}:
                    continue
                entries.append(item.name + ("/" if item.is_dir() else ""))
                if len(entries) >= 30:
                    break
        except Exception as exc:
            ui.warning(f"Failed to list project directory: {exc}", "Claude CLI")
            return instruction

        if not entries:
            return instruction

        context = (
            "\n\n<project_structure>\n"
            "Current files in project root:\n"
            + "\n".join(f"- {name}" for name in entries)
            + "\n</project_structure>"
        )
        return instruction + context

    def _build_content_blocks(
        self,
        instruction: str,
        images: List[Dict[str, Any]],
        project_repo_path: Path,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        blocks: List[Dict[str, Any]] = [{"type": "text", "text": instruction}]
        attachments_meta: List[Dict[str, Any]] = []

        for index, image in enumerate(images):
            img = _image_to_dict(image)
            name = img.get("name") or f"image_{index+1}"
            declared_mime = img.get("mime_type")

            base64_data = img.get("base64_data")
            path_value = img.get("path")
            raw_bytes: Optional[bytes] = None

            if not base64_data and path_value:
                file_path = Path(path_value)
                if not file_path.is_absolute():
                    file_path = project_repo_path / file_path
                try:
                    with open(file_path, "rb") as f:
                        raw_bytes = f.read()
                except Exception as exc:
                    ui.warning(f"Failed to read image {path_value}: {exc}", "Claude CLI")
                    continue
            else:
                if base64_data:
                    try:
                        raw_bytes = base64.b64decode(
                            _strip_data_url(str(base64_data)), validate=False
                        )
                    except Exception as exc:
                        ui.warning(f"Invalid base64 image {name}: {exc}", "Claude CLI")
                        continue

            if not raw_bytes:
                ui.warning(f"Skipping image {name}: no data provided", "Claude CLI")
                continue

            mime_type = self._detect_image_mime(raw_bytes, declared_mime)

            base64_clean = base64.b64encode(raw_bytes).decode("utf-8")

            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64_clean,
                    },
                }
            )
            attachments_meta.append(
                {
                    "name": name,
                    "mime_type": mime_type,
                    "size_bytes": len(raw_bytes),
                }
            )

        return blocks, attachments_meta

    def _tool_configuration(self, is_initial_prompt: bool) -> Tuple[List[str], List[str]]:
        base_tools = [
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Bash",
            "Glob",
            "Grep",
            "LS",
            "WebFetch",
            "WebSearch",
        ]
        if is_initial_prompt:
            return base_tools, ["TodoWrite"]
        return base_tools + ["TodoWrite"], []

    def _write_temp_settings(self, project_path: Path) -> Optional[Path]:
        settings_path = project_path / ".claude" / "settings.json"
        base_settings: Dict[str, Any] = {}
        if settings_path.exists():
            try:
                base_settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except Exception as exc:
                ui.warning(f"Failed to load project settings: {exc}", "Claude CLI")

        try:
            from app.services.claude_act import get_system_prompt

            system_prompt = get_system_prompt()
        except Exception as exc:  # pragma: no cover
            ui.warning(f"System prompt load failed: {exc}", "Claude CLI")
            system_prompt = (
                "You are Claude Code, an AI coding assistant specialized in building modern web applications."
            )

        base_settings["customSystemPrompt"] = system_prompt

        try:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            json.dump(base_settings, tmp, ensure_ascii=False)
            tmp.flush()
            tmp.close()
            ui.debug(f"Wrote temp settings to {tmp.name}", "Claude CLI")
            return Path(tmp.name)
        except Exception as exc:  # pragma: no cover
            ui.warning(f"Failed to create temp settings: {exc}", "Claude CLI")
            return None

    def _extract_text_from_blocks(self, blocks: List[Dict[str, Any]]) -> str:
        text_parts: List[str] = []
        for block in blocks or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)



    def _detect_image_mime(self, raw_bytes: bytes, declared: Optional[str]) -> str:
        """Infer MIME type from raw image bytes."""
        if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if raw_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if raw_bytes.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if raw_bytes.startswith(b"BM"):
            return "image/bmp"
        if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
            return "image/webp"
        return declared or "image/png"

    async def get_session_id(self, project_id: str) -> Optional[str]:
        return self._session_store.get(project_id)

    async def set_session_id(self, project_id: str, session_id: str) -> None:
        self._session_store[project_id] = session_id

    def _detect_image_mime(self, raw_bytes: bytes, declared: Optional[str]) -> str:
        # Minimal signature detection to avoid external dependencies
        if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if raw_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if raw_bytes.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if raw_bytes.startswith(b"BM"):
            return "image/bmp"
        if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
            return "image/webp"
        return declared or "image/png"


__all__ = ["ClaudeCodeCLI"]
