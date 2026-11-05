"""Settings, read from the environment and an optional .env file."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOME = Path.home() / ".prins"
HANDY_BINARY = Path("/Applications/Handy.app/Contents/MacOS/Handy")
HANDY_HOOK_PATH = (
    Path.home() / "Library/Application Support/com.pais.handy/hooks/transcription"
)


def load_dotenv(path: Path) -> None:
    """Load KEY=value lines. Values already in the environment win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        if value:
            os.environ.setdefault(key.strip(), value)


@dataclass
class Config:
    home: Path = DEFAULT_HOME
    http_port: int = 8737
    model: str = "claude-haiku-5-5"
    printer: str = "preview"
    printer_port: str = ""
    printer_baud: int = 9600
    printer_bytes_per_sec: int = 900
    printer_dots: int = 384
    m110_url: str = "http://127.0.0.1:8110"
    board_port: str = ""
    label_model: str = "claude-sonnet-5-5"
    name: str = ""  # The owner's name, for the FROM line on a poster sent to a friend.
    label_printer_url: str = "http://127.0.0.1:8110"
    stt_model: str = "turbo"
    stt_language: str = ""
    handy_binary: Path = HANDY_BINARY
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_owner: str = ""
    imap_host: str = ""
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    cloud_url: str = ""
    cloud_token: str = ""
    agent_auto_print: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ.get
        return cls(
            home=Path(env("PRINS_HOME", str(DEFAULT_HOME))),
            http_port=int(env("PRINS_HTTP_PORT", "8737")),
            model=env("PRINS_MODEL", "claude-haiku-5-5"),
            printer=env("PRINS_PRINTER", "preview"),
            printer_port=env("PRINS_PRINTER_PORT", ""),
            printer_baud=int(env("PRINS_PRINTER_BAUD", "9600")),
            printer_bytes_per_sec=int(env("PRINS_PRINTER_BYTES_PER_SEC", "900")),
            printer_dots=int(env("PRINS_PRINTER_DOTS", "384")),
            m110_url=env("PRINS_M110_URL", "http://127.0.0.1:8110"),
            board_port=env("PRINS_BOARD_PORT", ""),
            label_model=env("PRINS_LABEL_MODEL", "claude-sonnet-5-5"),
            name=env("PRINS_NAME", ""),
            label_printer_url=env("PRINS_LABEL_PRINTER_URL", "http://127.0.0.1:8110"),
            stt_model=env("PRINS_STT_MODEL", "turbo"),
            stt_language=env("PRINS_STT_LANGUAGE", ""),
            handy_binary=Path(env("PRINS_HANDY_BINARY", str(HANDY_BINARY))),
            slack_bot_token=env("SLACK_BOT_TOKEN", ""),
            slack_app_token=env("SLACK_APP_TOKEN", ""),
            slack_owner=env("PRINS_SLACK_OWNER", ""),
            imap_host=env("PRINS_IMAP_HOST", ""),
            imap_user=env("PRINS_IMAP_USER", ""),
            imap_password=env("PRINS_IMAP_PASSWORD", ""),
            imap_folder=env("PRINS_IMAP_FOLDER", "INBOX"),
            cloud_url=env("PRINS_CLOUD_URL", ""),
            cloud_token=env("PRINS_CLOUD_TOKEN", ""),
            agent_auto_print=env("PRINS_AGENT_AUTO_PRINT", "").lower() in ("1", "true", "yes"),
        )

    @property
    def db_path(self) -> Path:
        return self.home / "prins.db"

    @property
    def prints_dir(self) -> Path:
        return self.home / "prints"

    @property
    def labels_dir(self) -> Path:
        return self.home / "labels"

    @property
    def token_path(self) -> Path:
        return self.home / "token"

    def api_token(self) -> str:
        """The shared secret local clients send. Created on first use, readable only by you."""
        self.home.mkdir(parents=True, exist_ok=True)
        if self.token_path.exists():
            return self.token_path.read_text().strip()
        token = secrets.token_urlsafe(24)
        self.token_path.touch(mode=0o600)
        self.token_path.write_text(token)
        return token
