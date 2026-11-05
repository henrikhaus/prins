"""Slack over Socket Mode, so the laptop needs no public URL.

What creates a note:
- a direct message to the bot
- an @mention of the bot in a channel it is in
- the owner reacting with :printer: to a message in a channel the bot is in

The app manifest is in docs/slack-manifest.yaml. Requires the `slack` extra.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger(__name__)
PRINT_REACTION = "printer"


@dataclass(frozen=True)
class SlackMessage:
    sender_id: str
    text: str
    external_id: str


def from_message_event(event: dict) -> Optional[SlackMessage]:
    """A direct message to the bot, or None for anything that is not a person's new DM."""
    if event.get("channel_type") != "im":
        return None
    if event.get("bot_id") or event.get("subtype"):  # Edits, joins, and the bot's own posts.
        return None
    return _message(event.get("user", ""), event.get("text", ""), event.get("channel", ""), event.get("ts", ""))


def from_mention_event(event: dict) -> Optional[SlackMessage]:
    return _message(event.get("user", ""), event.get("text", ""), event.get("channel", ""), event.get("ts", ""))


def reaction_target(event: dict, owner: str) -> Optional[tuple[str, str]]:
    """(channel, ts) of the message to fetch, if this reaction should create a note.

    Only the owner counts. Otherwise anyone in the workspace could print on their desk.
    """
    if not owner or event.get("user") != owner or event.get("reaction") != PRINT_REACTION:
        return None
    item = event.get("item", {})
    if item.get("type") != "message":
        return None
    return item.get("channel", ""), item.get("ts", "")


def _message(user: str, text: str, channel: str, ts: str) -> Optional[SlackMessage]:
    if not user or not text.strip() or not channel or not ts:
        return None
    return SlackMessage(sender_id=user, text=text, external_id=f"{channel}:{ts}")


def run_slack(
    *,
    bot_token: str,
    app_token: str,
    owner: str,
    ingest: Callable[..., None],
) -> None:
    """Blocks forever, so run it on its own thread."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    from slack_sdk.errors import SlackApiError

    app = App(token=bot_token)
    names: dict[str, str] = {}

    def display_name(client, user_id: str) -> str:
        if user_id not in names:
            try:
                profile = client.users_info(user=user_id)["user"]["profile"]
                names[user_id] = profile.get("display_name") or profile.get("real_name") or user_id
            except SlackApiError as exc:
                log.warning("Could not look up Slack user %s: %s", user_id, exc)
                return user_id
        return names[user_id]

    def forward(client, message: Optional[SlackMessage]) -> None:
        if message is not None:
            ingest(
                source="slack",
                sender=display_name(client, message.sender_id),
                text=message.text,
                external_id=message.external_id,
            )

    @app.event("message")
    def on_message(event, client):
        forward(client, from_message_event(event))

    @app.event("app_mention")
    def on_mention(event, client):
        forward(client, from_mention_event(event))

    @app.event("reaction_added")
    def on_reaction(event, client):
        target = reaction_target(event, owner)
        if target is None:
            return
        channel, ts = target
        try:
            found = client.conversations_replies(channel=channel, ts=ts, limit=1, inclusive=True)
        except SlackApiError as exc:
            log.warning("Could not fetch the reacted message: %s", exc)
            return
        for raw in found.get("messages", [])[:1]:
            forward(client, _message(raw.get("user", ""), raw.get("text", ""), channel, ts))

    SocketModeHandler(app, app_token).start()
