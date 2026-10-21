#!/usr/bin/env python
import re
import sys
import json
import os
import urllib.request
import subprocess
import pathlib


def run_or_die(command: str):
    state = os.system(command)
    if state != 0:
        sys.exit(state)


NGROK_TARGET_PORT = re.search(
    "host.docker.internal:([0-9]+)", pathlib.Path("docker-compose.yaml").read_text()
).group(1)

# set some fake stuff to make sure we're not touching production
os.environ["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
os.environ["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

os.chdir(os.path.normpath(os.path.join(__file__, "..")))
run_or_die("docker compose create")
run_or_die("docker compose start")
run_or_die("sam build")

# set up dynamodb, mirroring the tables and initial items in terraform/dynamo.tf.
# Table names must match the DYNAMO_*_TABLE_NAME variables in template.yaml.
DYNAMO_TABLES = {
    "barbot-local-table": {"id": {"S": "current"}, "venues": {"M": {}}, "poll_id": {"N": "0"}},
    "barbot-local-events": {"id": {"S": "current"}, "events": {"M": {}}},
}
for table_name, initial_item in DYNAMO_TABLES.items():
    state = os.system(
        f"aws dynamodb create-table --table-name {table_name} --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH --billing-mode PAY_PER_REQUEST --endpoint-url http://localhost:8000 > /dev/null"
    )
    # Only seed newly created tables so existing local data is kept.
    if state == 0:
        run_or_die(f"aws dynamodb put-item --table-name {table_name} --endpoint-url http://localhost:8000 --item '{json.dumps(initial_item)}'")

run_or_die("./set-webhook.py local")
os.execvp(
    "sam",
    [
        "sam",
        "local",
        "start-api",
        "--host",
        "0.0.0.0",
        "--docker-network",
        "barbot",
        "--port",
        NGROK_TARGET_PORT,
        "--env-vars",
        "env.json",
        "--warm-containers",
        "EAGER",
    ],
)
