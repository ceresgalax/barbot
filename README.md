# barbot

## Running Locally

0. Ensure the `[aws](https://aws.amazon.com/cli/)` and `[sam](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)` CLI tools are install.

1. Create a file at the root of the repo named `env.json`.

This is the environment file used by AWS SAM for setting the function's environment variables.
The file will look something like this:

```
{
  "WebhookFunction": {
    "MAIN_CHAT_ID": "<XXXXX>",
    "TELEGRAM_BOT_TOKEN": "<XXXXX>:<XXXXX>",
    "BAR_SPREADSHEET": "https://docs.google.com/spreadsheets/d/<XXXXX>/"
  }
}
```

**Make sure the telegram bot and main chat id in `env.json` are different than the live bot's**.
Local development will nuke the webhook information for that bot.

2. Set the `NGROK_AUTHTOKEN` enviornment variable.

You need a [free ngrok token](https://ngrok.com/) for development - this is so telegram can talk to your local webhook handler.

3. Run `./run-local.py`

This takes care of setting up the helper services, building the application, running it, and pointing telegram to the local instance.
