# Connectors

Only Slack and email exist today. None of them have been run against a real account yet: the tests use recorded event shapes and a fake mail server.

## Slack

No public URL or server is needed, since it uses Socket Mode.

1. At [api.slack.com/apps](https://api.slack.com/apps), choose **Create New App**, then **From a manifest**, and paste [slack-manifest.yaml](slack-manifest.yaml).
2. Under **Basic Information**, create an app-level token with the `connections:write` scope. That is `SLACK_APP_TOKEN` (`xapp-...`).
3. Install the app to your workspace. The bot token is `SLACK_BOT_TOKEN` (`xoxb-...`).
4. Set `PRINS_SLACK_OWNER` to your member ID, from your Slack profile under **Copy member ID**.
5. Invite the bot to any channel you want to use.

| You do this | You get |
|---|---|
| DM the bot | A note |
| @mention the bot | A note |
| React with :printer: to a message in a channel with the bot | A note, if you're the owner |

**It can't see your personal DMs or every channel.** That's a limit of bot tokens. Reading someone's whole Slack needs a user token and a bigger trust conversation, so test demand first.

## Email

Polls every 60 seconds. Read-only: nothing gets marked read, moved or deleted. Newsletters are skipped before the model runs. The first run starts from now rather than importing your inbox.

```sh
PRINS_IMAP_HOST=imap.gmail.com
PRINS_IMAP_USER=you@example.com
PRINS_IMAP_PASSWORD=your-app-password   # An app password, not your login
```

| Provider | Status |
|---|---|
| Gmail, iCloud, Fastmail | Should work with an app password |
| Microsoft 365, Outlook.com | **Won't work.** They need OAuth, which isn't built |
| Corporate Google Workspace | Admins can disable IMAP or app passwords |

## Microsoft Teams

**Not built.** It needs Microsoft Graph and usually tenant admin consent, so it's a sales conversation as much as a code task. Add it when a paying customer asks for it. It would be one file in `connectors/` calling `engine.ingest`, like the others.

## Your own source

Anything that can make an HTTP call can add a note, including a coding agent that's blocked and needs a decision. See the HTTP API in [ARCHITECTURE.md](ARCHITECTURE.md).
