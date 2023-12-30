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

# set up dynamodb
state = os.system(
    "aws dynamodb create-table --table-name barbot-local-table --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH --provisioned-throughput ReadCapacityUnits=10,WriteCapacityUnits=10 --endpoint-url http://localhost:8000"
)
if state == 0:
    run_or_die("""aws dynamodb update-item --table-name barbot-local-table --endpoint-url http://localhost:8000 --key '{"id": {"S": "current"}}' --update-expression 'SET venues = :empty' --expression-attribute-values '{":empty": {"M": {}}}'""")
    run_or_die("""aws dynamodb update-item --table-name barbot-local-table --endpoint-url http://localhost:8000 --key '{"id": {"S": "current"}}' --update-expression 'SET poll_id = :p' --expression-attribute-values '{":p": {"N": "0"}}'""")

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
