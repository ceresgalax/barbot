# barbot

Barbot is a Telegram bot that automates decision-making for our weekly bar night.

## Running the Bot Locally

0. Ensure the [aws](https://aws.amazon.com/cli/) and [sam](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) CLI tools are installed.

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

## Building & Deploying

1. Install the version of python currently being targeted by the lambda runtime (See lambda.tf. At the time of writing, this is Python 3.12)

2. Create a virtual environment using that python version. `python3.12 -m venv venv`

3. Activate the virtual environment and run ./build.py

4. In the `terraform` directory, Copy a template .tfvars file to terraform.tfvars. Set the empty values.

5. Use `terraform workspace show` and `terraform workspace select` to choose the correct terraform state to use. 
   `default` workspace is used for prod, and `test` is used for the 'testing' bot and channel.

## Deploying with GitHub Actions

The `Deploy` workflow (`.github/workflows/deploy.yml`) deploys to one of two GitHub Environments:

| GitHub Environment | Triggered by                                   | Terraform workspace | Base tfvars              |
|--------------------|------------------------------------------------|---------------------|--------------------------|
| `production`       | Pushing a `v*` tag, or running manually        | `default`           | `base.prod.tfvars`       |
| `testing`          | Running manually (Actions → Deploy → Run workflow) | `test`          | `base.test.tfvars`       |

Each environment needs its own copy of these secrets (Settings → Environments → *environment* → Environment secrets):

- `ACTIONS_ROLE_ARN`
- `TELEGRAM_BOT_TOKEN`
- `MAIN_CHAT_ID`
- `BAR_SPREADSHEET`
- `SELENIUM_SERVER_URL`
- `ANNOUNCEMENT_CHAT_ID`

The secret names are the same in both environments; the workflow picks up whichever set belongs to the environment it is deploying to.
