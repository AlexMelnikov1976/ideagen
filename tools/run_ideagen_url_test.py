#!/usr/bin/env python3
"""Run one URL through IdeaGen v2 without leaving the workflow active.

The script downloads public YouTube metadata/transcript locally, adds a
temporary n8n webhook branch, activates the workflow only for the request,
captures the filtered result, then deactivates and restores the workflow.
"""

import argparse
import json
import ssl
import subprocess
import tempfile
import urllib.request
from pathlib import Path


WORKFLOW_ID = "yq3FunHR5eitjZSO"
BASE_URL = "https://melnikov.app.n8n.cloud/api/v1"
WEBHOOK_PATH = "ideagen-url-test-20260712"
WEBHOOK_URL = f"https://melnikov.app.n8n.cloud/webhook/{WEBHOOK_PATH}"
ENV_FILE = Path.home() / "Developer" / "b360" / ".b360.env"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def api_key() -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("N8N_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("N8N_API_KEY not found")


def api(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={
            "X-N8N-API-KEY": api_key(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, context=CTX, timeout=90) as response:
        return json.loads(response.read() or "null")


def workflow_payload(workflow: dict) -> dict:
    return {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow.get("settings", {}),
    }


def youtube_payload(url: str) -> dict:
    metadata = json.loads(
        subprocess.check_output(
            ["yt-dlp", "--skip-download", "--dump-single-json", "--no-warnings", url],
            text=True,
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        output = str(Path(tmp) / "%(id)s")
        subprocess.run(
            [
                "yt-dlp", "--skip-download", "--write-auto-subs",
                "--sub-lang", "ru-orig", "--sub-format", "json3",
                "--no-warnings", "-o", output, url,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subtitle = Path(tmp) / f"{metadata['id']}.ru-orig.json3"
        captions = json.loads(subtitle.read_text())
        transcript = "".join(
            segment.get("utf8", "")
            for event in captions.get("events", [])
            for segment in event.get("segs", [])
        )
    return {
        "videoId": metadata["id"],
        "videoUrl": url,
        "title": metadata.get("title", ""),
        "channel": metadata.get("channel", ""),
        "description": metadata.get("description", ""),
        "publishedAt": metadata.get("upload_date", ""),
        "transcript": transcript[:12000],
        "skip": False,
    }


def add_temporary_branch(workflow: dict, persist: bool):
    temporary_nodes = [
        {
            "name": "URL test webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [-500, 700],
            "webhookId": "ideagen-url-test-20260712",
            "parameters": {
                "httpMethod": "POST",
                "path": WEBHOOK_PATH,
                "responseMode": "lastNode" if persist else "responseNode",
                "options": {},
            },
        },
        {
            "name": "Normalize URL test",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-50, 700],
            "parameters": {
                "jsCode": "const body = $('URL test webhook').first().json.body || {};\nconst cfg = $('API Keys and Config').first().json;\nreturn [{json:{...body, min_score: Math.max(Number(cfg.MIN_SCORE || 7), 7), claude_model: cfg.CLAUDE_MODEL || 'gpt-4o'}}];"
            },
        },
    ]
    if not persist:
        temporary_nodes.append({
            "name": "Respond URL test",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.4,
            "position": [1050, 700],
            "parameters": {
                "respondWith": "json",
                "responseBody": "={{ $json }}",
                "options": {},
            },
        })
    workflow["nodes"].extend(temporary_nodes)
    workflow["connections"]["URL test webhook"] = {
        "main": [[{"node": "API Keys and Config", "type": "main", "index": 0}]]
    }
    workflow["connections"]["API Keys and Config"] = {
        "main": [[{"node": "Normalize URL test", "type": "main", "index": 0}]]
    }
    workflow["connections"]["Normalize URL test"] = {
        "main": [[{"node": "Подготовить запрос к Claude", "type": "main", "index": 0}]]
    }
    if not persist:
        workflow["connections"]["Парсить и фильтровать идеи"] = {
            "main": [[{"node": "Respond URL test", "type": "main", "index": 0}]]
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--persist", action="store_true", help="write passed candidate to Notion")
    args = parser.parse_args()

    original = api("GET", f"/workflows/{WORKFLOW_ID}")
    if original.get("active"):
        raise RuntimeError("Workflow must be inactive before the controlled test")
    test_workflow = json.loads(json.dumps(original))
    add_temporary_branch(test_workflow, args.persist)

    result = None
    try:
        api("PUT", f"/workflows/{WORKFLOW_ID}", workflow_payload(test_workflow))
        api("POST", f"/workflows/{WORKFLOW_ID}/activate")
        payload = youtube_payload(args.url)
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, context=CTX, timeout=180) as response:
            result = json.loads(response.read() or "null")
    finally:
        try:
            api("POST", f"/workflows/{WORKFLOW_ID}/deactivate")
        finally:
            api("PUT", f"/workflows/{WORKFLOW_ID}", workflow_payload(original))

    safe_result = {
        key: value for key, value in (result or {}).items()
        if key not in {"openai_api_key", "claude_body", "anthropic_api_key", "notion_api_key"}
    }
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
