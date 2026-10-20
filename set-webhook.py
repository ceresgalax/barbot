#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request
import subprocess


docker_compose_path = os.path.normpath(os.path.join(__file__, '..', 'docker-compose.yaml'))

NGROK_TARGET_PORT = re.search('host.docker.internal:([0-9]+)', pathlib.Path(docker_compose_path).read_text()).group(1)

os.chdir(os.path.normpath(os.path.join(__file__, '..')))


def get_data_from_terraform():
    p = subprocess.run(
        ["terraform", "output", "-json"],
        cwd="./terraform",
        stdout=subprocess.PIPE,
        text=True,
    )
    outputs = json.loads(p.stdout)
    bot_token = outputs["telegram_bot_token"]["value"]
    webhook_url = outputs["webhook_url"]["value"]
    webhook_secret = outputs["webhook_secret"]["value"]
    return bot_token, webhook_url, webhook_secret


def get_data_from_local():
    with open("env.json", "r") as handle:
        env = json.load(handle)
    bot_token = env["WebhookFunction"]["TELEGRAM_BOT_TOKEN"]
    with urllib.request.urlopen("http://localhost:4040/api/tunnels") as response:
        data = json.loads(response.read())
    base_url = [
        t["public_url"] for t in data["tunnels"] if t["config"]["addr"].endswith(f":{NGROK_TARGET_PORT}")
    ][0]
    webhook_url = base_url + "/webhook"
    webhook_secret = "NONE"
    return bot_token, webhook_url, webhook_secret


COMMANDS = [
    {'command': 'start', 'description': 'How to use barbot'},
    {'command': 'list', 'description': 'List the current suggestions'},
    {'command': 'map', 'description': 'Show a map of the current suggestions'},
    {'command': 'delete', 'description': 'Delete one of your suggestions'},
    {'command': 'newevent', 'description': 'Create a scheduled event (admins only)'},
    {'command': 'delevent', 'description': 'Delete a scheduled event (admins only)'},
]


def telegram_post(bot_token, method, payload):
    request = urllib.request.Request(
        url=f'https://api.telegram.org/bot{bot_token}/{method}',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'barbot by @ceresgalax'
        },
        method='POST'
    )

    with urllib.request.urlopen(request) as response:
        if response.status < 200 or response.status >= 300:
            print(f'Failed to call {method}')
            exit(1)


parser = argparse.ArgumentParser()
parser.add_argument("context", choices=["terraform", "local"])


def main():
    args = parser.parse_args()
    if args.context == "terraform":
        fn = get_data_from_terraform
    elif args.context == "local":
        fn = get_data_from_local
    else:
        sys.exit(2)
    bot_token, webhook_url, webhook_secret = fn()
    print(f"Webhook URL: {webhook_url}")

    telegram_post(bot_token, 'setWebhook', {
        'url': webhook_url,
        'secret_token': webhook_secret
    })

    telegram_post(bot_token, 'deleteMyCommands', {'scope': {'type': 'default'}})
    telegram_post(bot_token, 'deleteMyCommands', {'scope': {'type': 'all_group_chats'}})
    telegram_post(bot_token, 'setMyCommands', {
        'scope': {'type': 'all_private_chats'},
        'commands': COMMANDS,
    })


if __name__ == "__main__":
    main()
