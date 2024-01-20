# barbot

## Running the Bot Locally

0. Ensure the `[aws](https://aws.amazon.com/cli/)` and `[sam](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)` CLI tools are install.

1. Create a file at the root of the repo named `env.json`.

This is the environment file used by AWS SAM for setting the function's environment variables.
The file will look something like this:

```
{
  "WebhookFunction": {
    "MAIN_CHAT_ID": "<XXXXX>",
    "TELEGRAM_BOT_TOKEN": "<XXXXX>:<XXXXX>",
    "BAR_SPREADSHEET": "https://docs.google.com/spreadsheets/d/<XXXXX>/",
    "SELENIUM_SERVER_URL": "http://<XXXXX>:4444"
  }
}
```

**Make sure the telegram bot and main chat id in `env.json` are different than the live bot's**.
Local development will nuke the webhook information for that bot.

2. Set the `NGROK_AUTHTOKEN` enviornment variable.

You need a [free ngrok token](https://ngrok.com/) for development - this is so telegram can talk to your local webhook handler.

3. Run `./run-local.py`

This takes care of setting up the helper services, building the application, running it, and pointing telegram to the local instance.

### Invoking Scheduled Events Locally

1. Duplicate the `"WebhookFunction"` object in `env.json` under the key `SequenceFunction`.

This is an unfortunate limitation of SAM:

```
{
  "WebhookFunction": {"a": "b", "c": "d"},
  "SequenceFunction": {"a": "b", "c": "d"},
}
```

2. Run `sam local invoke`

*WARNING*: Make sure you've run `./run-local.py` before invoking sam, because `./run-local.py` is what builds the image that sam uses (otherwise, you'll be using an outdated barbot).

An invocation should look something like this:

```
echo '{"barnight_event_type": "CreatePoll"}' | sam local invoke SequenceFunction --docker-network barbot --env-vars env.json -e -
```
