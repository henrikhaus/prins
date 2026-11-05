"""Command line: `prins run`, `labels`, `label-draw`, `mic-test`, `mcp`, `doctor`, `send`, `test-print`, `install-hook`, `screen-test`."""

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
from .design.designer import Designer
from .device import AtechDevice, CardView, Device, SimDevice, StatusView
from .engine import Engine
from .labelprinter import LabelPrinter, PrinterError, PrinterServer
from .handy import Handy
from .printers import AtechPrinter, M110Printer, PreviewPrinter, Printer, SerialPrinter
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
        return SerialPrinter(cfg.printer_port, cfg.printer_baud, cfg.printer_bytes_per_sec, cfg.printer_dots)
    if cfg.printer == "atech":
        if not isinstance(device, AtechDevice):
            sys.exit("PRINS_PRINTER=atech needs the real board, not --device sim.")
        return AtechPrinter(device.call, device.query, cfg.printer_baud, cfg.printer_bytes_per_sec, paper_dots=cfg.printer_dots)
    if cfg.printer == "m110":
        return M110Printer(cfg.m110_url)
    if cfg.printer != "preview":
        sys.exit(f"Unknown PRINS_PRINTER {cfg.printer!r}. Use m110, preview, atech or serial.")
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


def _start_cloud(device_kind: str, cfg: Config, engine: Engine, store: Store) -> None:
    if not (cfg.cloud_url and cfg.cloud_token):
        return
    from . import __version__
    from .cloud import CloudSync

    handy = Handy(cfg.handy_binary)

    def status() -> dict:
        state = engine.state()
        return {
            "deviceKind": device_kind,
            "printer": cfg.printer,
            "handyInstalled": handy.installed,
            "slack": bool(cfg.slack_bot_token and cfg.slack_app_token),
            "email": bool(cfg.imap_host and cfg.imap_user and cfg.imap_password),
            "mode": state["mode"],
            "queue": state["queue"],
            "version": __version__,
        }

    try:
        sync = CloudSync(cfg.cloud_url, cfg.cloud_token, store, engine, status)
    except ValueError as exc:
        sys.exit(str(exc))
    threading.Thread(target=sync.run, name="cloud", daemon=True).start()
    log.info("Syncing with %s.", cfg.cloud_url)


def cmd_run(args: argparse.Namespace, cfg: Config) -> int:
    store = Store(cfg.db_path)
    device = _make_device(args.device, cfg)
    triage = Triage.from_env(cfg.model)
    engine = Engine(
        store=store,
        triage=triage,
        device=device,
        printer=_make_printer(cfg, device),
        dictation=Handy(cfg.handy_binary),
        designer=Designer(triage.client, cfg.model),
        agent_auto_print=cfg.agent_auto_print,
    )
    token = cfg.api_token()
    try:
        server = make_server(engine, token, cfg.http_port)
    except OSError as exc:
        sys.exit(f"Could not listen on port {cfg.http_port}: {exc}. Is Prins already running?")
    serve_in_background(server)
    _start_connectors(cfg, engine, store)
    engine.start()
    _start_cloud(args.device, cfg, engine, store)
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


def cmd_labels(args: argparse.Namespace, cfg: Config) -> int:
    """The label maker: starts the printer server and the board loop together."""
    from .labelboard import LabelBoard
    from .labeldesigner import LabelDesigner
    from .labels import LabelMaker
    from .stt import WhisperTranscriber

    printer = LabelPrinter(cfg.label_printer_url, dry_run=args.dry_run)
    server = PrinterServer(printer)
    if not args.no_server:
        try:
            server.start()
        except PrinterError as exc:
            log.warning("%s Designs still work and are saved to %s, but printing will fail.", exc, cfg.labels_dir)
    designer = LabelDesigner.from_env(cfg.label_model, web=not args.no_web)
    stt = WhisperTranscriber(cfg.stt_model, cfg.stt_language)

    def warm() -> None:
        try:
            stt.warm()
        except Exception as exc:
            log.error("Speech to text is not ready: %s", exc)

    threading.Thread(target=warm, name="whisper-warmup", daemon=True).start()
    device = LabelBoard(cfg.board_port)
    LabelMaker(device, stt, designer, printer, save_dir=cfg.labels_dir).start()
    log.info("Label maker running%s. Hold button 5 and talk.", " (dry run: nothing is printed)" if args.dry_run else "")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        device.close()
        server.stop()
    return 0


def cmd_label_draw(args: argparse.Namespace, cfg: Config) -> int:
    """Ask the drawing agent for a design without any hardware. Saves a PNG and prints the shapes."""
    from .design import DesignError
    from .labeldesigner import Design, LabelDesigner

    designer = LabelDesigner.from_env(cfg.label_model, web=not args.no_web)
    try:
        current = Design.from_ops(json.loads(Path(args.start_from).read_text())) if args.start_from else None
        design = designer.design(args.instruction, current)
    except (DesignError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else cfg.labels_dir / f"draw-{time.strftime('%Y%m%d-%H%M%S')}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    design.image.save(out)
    print(json.dumps(design.ops, indent=1))
    print(f"{design.title}: {design.summary}\nWarnings: {design.warnings or 'none'}\nSaved {out}", file=sys.stderr)
    return 0


def cmd_mic_test(args: argparse.Namespace, cfg: Config) -> int:
    """Hold button 5, talk, and hear the board's microphone played back."""
    from . import mictest

    try:
        mictest.run(cfg.board_port, cfg.home / "mic-tests", args.boosted)
    except KeyboardInterrupt:
        pass
    return 0


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
    image = render_note(item)
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


def cmd_mcp(args: argparse.Namespace, cfg: Config) -> int:
    from .mcp_server import run_mcp

    return run_mcp(cfg)


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
    if cfg.printer == "m110":
        up = M110Printer(cfg.m110_url).reachable()
        line(up, "Printer", "M110 server is running" if up else "M110 server isn't running: cd printer && uv run server.py")
    else:
        line(True, "Printer", cfg.printer + (f" on {cfg.printer_port}" if cfg.printer_port else ""))
    import importlib.util

    stt_ok = importlib.util.find_spec("faster_whisper") is not None
    line(stt_ok, "Speech to text", f"Whisper {cfg.stt_model}" if stt_ok else 'not installed: pip install -e ".[labels]"')
    printer_up = LabelPrinter(cfg.label_printer_url).reachable()
    line(printer_up, "Label printer server", cfg.label_printer_url if printer_up else "not running, `prins labels` starts it")
    line(bool(cfg.slack_bot_token and cfg.slack_app_token), "Slack", "configured" if cfg.slack_bot_token else "not configured")
    if cfg.slack_bot_token and not cfg.slack_owner:
        line(False, "Slack owner", "PRINS_SLACK_OWNER is empty, so :printer: reactions do nothing")
    line(bool(cfg.imap_host), "Email", cfg.imap_user or "not configured")
    line(bool(cfg.cloud_url and cfg.cloud_token), "Dashboard", cfg.cloud_url or "not configured")
    return 0


def main(argv: list[str] | None = None) -> int:
    # An MCP client starts this from anywhere, so the working directory can't be the only place.
    for folder in (Path.cwd(), Path(__file__).resolve().parents[2], Config.from_env().home):
        load_dotenv(folder / ".env")
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

    labels = sub.add_parser("labels", help="the label maker: talk to design a label, print it from the board")
    labels.add_argument("--dry-run", action="store_true", help="the printer server accepts prints but prints nothing")
    labels.add_argument("--no-web", action="store_true", help="the drawing agent may not search or read the web")
    labels.add_argument("--no-server", action="store_true", help="do not start printer/server.py, it is running already")
    labels.set_defaults(func=cmd_labels)
    draw = sub.add_parser("label-draw", help="ask the drawing agent for one label design, without the board")
    draw.add_argument("instruction")
    draw.add_argument("--from", dest="start_from", help="a JSON file of shapes to revise")
    draw.add_argument("--no-web", action="store_true", help="the agent may not search or read the web")
    draw.add_argument("-o", "--output", help="where to save the PNG")
    draw.set_defaults(func=cmd_label_draw)
    mic = sub.add_parser("mic-test", help="hold button 5 and hear what the board's microphone picked up")
    mic.add_argument("--boosted", action="store_true", help="play what Whisper hears (level raised) instead of the raw sound")
    mic.set_defaults(func=cmd_mic_test)
    sub.add_parser("test-print", help="print one test note").set_defaults(func=cmd_test_print)
    screen = sub.add_parser("screen-test", help="show every screen state on the board")
    screen.add_argument("--seconds", type=float, default=4.0)
    screen.set_defaults(func=cmd_screen_test)
    sub.add_parser("install-hook", help="connect Handy to Prins").set_defaults(func=cmd_install_hook)
    sub.add_parser("doctor", help="show what is ready").set_defaults(func=cmd_doctor)
    sub.add_parser("mcp", help="run the MCP server for Claude, Codex and others").set_defaults(func=cmd_mcp)

    args = parser.parse_args(argv)
    return args.func(args, Config.from_env())


if __name__ == "__main__":
    sys.exit(main())
