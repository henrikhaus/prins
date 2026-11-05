"""Command line: `prins run`, `doctor`, `send`, `test-print`, `install-hook`, `screen-test`."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import HANDY_HOOK_PATH, Config, load_dotenv
from .device import AtechDevice, CardView, Device, SimDevice, StatusView
from .engine import Engine
from .handy import Handy
from .printers import AtechPrinter, PreviewPrinter, Printer, SerialPrinter
from .render import render_note
from .server import TOKEN_HEADER, make_server, serve_in_background
from .store import Item, Store
from .triage import Triage

log = logging.getLogger("prins")
_REFRESH_S = 1.0


def _make_device(kind: str, cfg: Config) -> Device:
    return SimDevice() if kind == "sim" else AtechDevice(cfg.board_port)


def _make_printer(cfg: Config, device: Device) -> Printer:
    if cfg.printer == "serial":
        if not cfg.printer_port:
            sys.exit("PRINS_PRINTER=serial needs PRINS_PRINTER_PORT. List ports: ls /dev/cu.*")
        return SerialPrinter(cfg.printer_port, cfg.printer_baud, cfg.printer_bytes_per_sec)
    if cfg.printer == "atech":
        if not isinstance(device, AtechDevice):
            sys.exit("PRINS_PRINTER=atech needs the real board, not --device sim.")
        return AtechPrinter(device.call, device.query, cfg.printer_baud, cfg.printer_bytes_per_sec)
    if cfg.printer != "preview":
        sys.exit(f"Unknown PRINS_PRINTER {cfg.printer!r}. Use preview, atech or serial.")
    return PreviewPrinter(cfg.prints_dir)


def _start_connectors(cfg: Config, engine: Engine, store: Store) -> None:
    if cfg.slack_bot_token and cfg.slack_app_token:
        from .connectors.slack import run_slack

        def slack() -> None:
            try:
                run_slack(
                    bot_token=cfg.slack_bot_token,
                    app_token=cfg.slack_app_token,
                    owner=cfg.slack_owner,
                    ingest=engine.ingest,
                )
            except Exception:
                log.exception("Slack connector stopped")

        threading.Thread(target=slack, name="slack", daemon=True).start()
        log.info("Slack connector started.")

    if cfg.imap_host and cfg.imap_user and cfg.imap_password:
        from .connectors.email_imap import ImapPoller

        poller = ImapPoller(
            host=cfg.imap_host, user=cfg.imap_user, password=cfg.imap_password,
            folder=cfg.imap_folder, store=store, ingest=engine.ingest,
        )
        threading.Thread(target=poller.run, name="imap", daemon=True).start()
        log.info("Email connector started for %s.", cfg.imap_user)


def cmd_run(args: argparse.Namespace, cfg: Config) -> int:
    store = Store(cfg.db_path)
    device = _make_device(args.device, cfg)
    engine = Engine(
        store=store,
        triage=Triage.from_env(cfg.model),
        device=device,
        printer=_make_printer(cfg, device),
        dictation=Handy(cfg.handy_binary),
        note_width=cfg.printer_dots,
    )
    token = cfg.api_token()
    try:
        server = make_server(engine, token, cfg.http_port)
    except OSError as exc:
        sys.exit(f"Could not listen on port {cfg.http_port}: {exc}. Is Prins already running?")
    serve_in_background(server)
    _start_connectors(cfg, engine, store)
    engine.start()
    log.info("Running. Local API on http://127.0.0.1:%s, printer: %s.", cfg.http_port, cfg.printer)

    def ticker() -> None:
        while True:
            time.sleep(_REFRESH_S)
            try:
                engine.refresh()
            except Exception:
                log.exception("Refresh failed")

    threading.Thread(target=ticker, name="refresh", daemon=True).start()
    try:
        if isinstance(device, SimDevice):
            _sim_prompt(device)
        else:
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        engine.close()
    return 0


def _sim_prompt(device: SimDevice) -> None:
    print("Sim keys: c = print, d = dismiss, t = hold or release talk, q = quit")
    talking = False
    for line in sys.stdin:
        key = line.strip().lower()
        if key == "q":
            return
        if key == "c":
            device.click("confirm")
        elif key == "d":
            device.click("dismiss")
        elif key == "t":
            talking = not talking
            device.press("talk", talking)


def cmd_send(args: argparse.Namespace, cfg: Config) -> int:
    body = {"text": args.text, "source": args.source, "sender": args.sender}
    request = urllib.request.Request(
        f"http://127.0.0.1:{cfg.http_port}/v1/messages",
        data=json.dumps(body).encode(),
        headers={TOKEN_HEADER: cfg.api_token(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(response.read().decode())
    except (urllib.error.URLError, OSError) as exc:
        print(f"Could not reach Prins. Is `prins run` going? {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_test_print(args: argparse.Namespace, cfg: Config) -> int:
    item = Item(
        id=0, source="test", sender="Prins", raw_text="", title="If you can read this, printing works",
        detail="Æ Ø Å ß é ñ: the note is an image, so every language prints.",
        priority="normal", due="", status="queued", engine="none", created_at=time.time(),
    )
    image = render_note(item, cfg.printer_dots)
    device: Device = SimDevice() if cfg.printer != "atech" else AtechDevice(cfg.board_port)
    try:
        print(_make_printer(cfg, device).print_image(image, "test"))
    finally:
        device.close()
    return 0


def cmd_screen_test(args: argparse.Namespace, cfg: Config) -> int:
    """Walk through every screen state on the real board, and report button presses."""
    device = AtechDevice(cfg.board_port)
    views = [
        CardView("slack", "Maria Hansen", "Send Maria the Q3 numbers before Friday's board call",
                 "She needs churn and net revenue on one slide.", 3),
        CardView("email", "Jonas", "Reply to the contract question", "", 12),
        CardView("voice", "", "Book the dentist", "Before the end of the month.", 2),
        CardView("idle", "", "All clear", "Hold the blue button to dictate a note", 0, "Blue: hold to talk"),
        StatusView("listening", "Listening...", "Release when you are done"),
        StatusView("thinking", "Thinking...", "Turning that into a note"),
        StatusView("printing", "Printing..."),
    ]
    device.start(lambda button, down: print(f"  {button}: {'pressed' if down else 'released'}"))
    print("Check each screen by eye. Press the buttons: their names should appear here.")
    try:
        for view in views:
            print(f"Showing {type(view).__name__}: {view.title}")
            device.call("ui_card" if isinstance(view, CardView) else "ui_status", view.payload())
            time.sleep(args.seconds)
    finally:
        device.close()
    return 0


def cmd_install_hook(args: argparse.Namespace, cfg: Config) -> int:
    source = Path(__file__).resolve().parents[2] / "scripts" / "handy-hook.sh"
    target = HANDY_HOOK_PATH
    if target.exists() and target.read_bytes() != source.read_bytes():
        backup = target.with_suffix(".before-prins")
        shutil.copy2(target, backup)
        print(f"You already had a hook. Saved it to {backup}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    cfg.api_token()
    print(f"Installed {target}")
    return 0


def cmd_doctor(args: argparse.Namespace, cfg: Config) -> int:
    """Says what is ready, without changing anything."""
    from atech.runtime.transport import discover_ports

    def line(ok: bool, name: str, detail: str) -> None:
        print(f"[{'ok' if ok else '--'}] {name}: {detail}")

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    line(has_key, "Model", f"{cfg.model}" if has_key else "no ANTHROPIC_API_KEY, notes use the plain fallback")
    boards = discover_ports()
    line(bool(boards), "Board", boards[0].device if boards else "not found on USB (use a data cable)")
    handy = Handy(cfg.handy_binary)
    line(handy.installed, "Handy", str(cfg.handy_binary) if handy.installed else "not installed: scripts/install-handy.sh")
    line(HANDY_HOOK_PATH.exists(), "Handy hook", str(HANDY_HOOK_PATH) if HANDY_HOOK_PATH.exists() else "not installed: prins install-hook")
    line(True, "Printer", cfg.printer + (f" on {cfg.printer_port}" if cfg.printer_port else ""))
    line(bool(cfg.slack_bot_token and cfg.slack_app_token), "Slack", "configured" if cfg.slack_bot_token else "not configured")
    if cfg.slack_bot_token and not cfg.slack_owner:
        line(False, "Slack owner", "PRINS_SLACK_OWNER is empty, so :printer: reactions do nothing")
    line(bool(cfg.imap_host), "Email", cfg.imap_user or "not configured")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path.cwd() / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(prog="prins", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="start the device")
    run.add_argument("--device", choices=["atech", "sim"], default="atech")
    run.set_defaults(func=cmd_run)

    send = sub.add_parser("send", help="put a message in the queue of a running device")
    send.add_argument("text")
    send.add_argument("--source", default="agent")
    send.add_argument("--sender", default="")
    send.set_defaults(func=cmd_send)

    sub.add_parser("test-print", help="print one test note").set_defaults(func=cmd_test_print)
    screen = sub.add_parser("screen-test", help="show every screen state on the board")
    screen.add_argument("--seconds", type=float, default=4.0)
    screen.set_defaults(func=cmd_screen_test)
    sub.add_parser("install-hook", help="connect Handy to Prins").set_defaults(func=cmd_install_hook)
    sub.add_parser("doctor", help="show what is ready").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args, Config.from_env())


if __name__ == "__main__":
    sys.exit(main())
