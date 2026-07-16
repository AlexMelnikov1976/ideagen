#!/usr/bin/env python3
"""Patch the inactive IdeaGen workflow into a bounded validation pipeline.

The script never activates the workflow. It removes Telegram delivery, limits
each run to five videos and at most one candidate per video, and changes the
analysis prompt from idea generation to evidence-aware hypothesis extraction.

Usage:
    python3 agents/patch_ideagen_v2.py --dry-run
    python3 agents/patch_ideagen_v2.py
"""

import argparse
import json
import ssl
import urllib.request
from pathlib import Path


WORKFLOW_ID = "yq3FunHR5eitjZSO"
BASE_URL = "https://melnikov.app.n8n.cloud/api/v1"
ENV_FILE = Path.home() / "Developer" / "b360" / ".b360.env"


def api_key() -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("N8N_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("N8N_API_KEY not found")


CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def request(method: str, path: str, body=None):
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
    with urllib.request.urlopen(req, context=CTX, timeout=60) as response:
        return json.loads(response.read() or "null")


ANALYSIS_CODE = r'''const d = $json;
const cfg = $('API Keys and Config').first().json;
const openai_api_key = cfg.OPENAI_API_KEY;
const model = d.claude_model || 'gpt-4o';
const min_score = Math.max(Number(d.min_score || 7), 7);

const systemPrompt = `You are an evidence-aware product analyst. Your job is not to maximize ideas. Return zero or one atomic, testable candidate from the source. Reject hype, duplicates, vague inspiration, and claims without a feasible test. Numbers from the video are claims, not verified facts. IMPORTANT: lack of independent confirmation is NOT a rejection reason for Research. When a relevant source-only claim names a tool, repository, or measurable outcome, create one Research candidate whose next_action is to verify the primary source or run a small benchmark. Independent confirmation is required only before Experiment. Respond only with valid JSON.`;

const userPrompt = `Analyze this source for Alexey's active work: AI automation, n8n, Codex/Claude Code, b360, Chicko Analytics, CINEMA360 and a personal knowledge system.

VIDEO: ${d.title || ''}
CHANNEL: ${d.channel || ''}
DESCRIPTION: ${(d.description || '').slice(0, 500)}

TRANSCRIPT:
${(d.transcript || '').slice(0, 12000)}

Return exactly this JSON schema:
{
  "relevance_score": <1-10>,
  "summary": "<2-3 factual sentences>",
  "key_quotes": [],
  "metrics": ["<claims from source, explicitly labelled unverified>"],
  "ideas": [
    {
      "title": "<one atomic testable hypothesis, max 10 words>",
      "description": "<what would change and why it fits an active project>",
      "category": "<Automation|Product|AI development|Knowledge|Marketing>",
      "impact": "<measurable outcome; write hypothesis if no baseline exists>",
      "implementation": ["<first reversible action>", "<measurement step>", "<decision step>"],
      "tools": ["<only tools actually needed>"],
      "difficulty": "<low|medium|high>",
      "time_to_implement": "<bounded estimate, maximum two weeks>",
      "expected_roi": "<hypothesis, never present it as verified>",
      "evidence_level": <0 source claim only | 1 primary source found | 2 independent confirmation>,
      "initial_stage": "<Research|Experiment>",
      "project_fit": <1-5>,
      "success_metric": "<numeric or binary go/no-go condition>",
      "next_action": "<one concrete action>",
      "score": <1-10>
    }
  ],
  "rejection_reason": "<required when ideas is empty>"
}

Return at most one idea. A candidate with evidence_level 0-1 must use initial_stage Research and name the exact primary-source or benchmark check as next_action. Do not reject a candidate merely because evidence_level is 0 or 1. Only evidence_level 2 may use Experiment. Return an empty ideas array unless score >= ${min_score}, project_fit >= 4, the verification is reversible, and it can be completed within two weeks.`;

const body = JSON.stringify({
  model,
  max_tokens: 2200,
  temperature: 0.1,
  messages: [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt }
  ]
});

return [{ json: { ...d, claude_body: body, openai_api_key } }];'''


PARSER_CODE = r'''const modelRaw = $json.choices?.[0]?.message?.content;
if (!modelRaw) throw new Error('No content in model response');

const meta = $('Подготовить запрос к Claude').item.json;
const minScore = Math.max(Number(meta.min_score || 7), 7);
const safeMeta = {
  videoId: String(meta.videoId || ''),
  videoUrl: String(meta.videoUrl || ''),
  title: String(meta.title || ''),
  channel: String(meta.channel || ''),
  publishedAt: String(meta.publishedAt || ''),
  min_score: minScore,
  claude_model: String(meta.claude_model || '')
};
let raw = modelRaw.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
let analysis;
try {
  analysis = JSON.parse(raw);
} catch (error) {
  const match = raw.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('No JSON in model response');
  analysis = JSON.parse(match[0]);
}

const ideas = (Array.isArray(analysis.ideas) ? analysis.ideas : [])
  .filter(idea => Number(idea.score) >= minScore && Number(idea.project_fit) >= 4)
  .slice(0, 1)
  .map(idea => ({
    title: String(idea.title || ''),
    description: String(idea.description || ''),
    category: String(idea.category || ''),
    impact: String(idea.impact || ''),
    implementation: Array.isArray(idea.implementation) ? idea.implementation.map(String).slice(0, 3) : [],
    tools: Array.isArray(idea.tools) ? idea.tools.map(String) : [],
    difficulty: String(idea.difficulty || 'medium'),
    time_to_implement: String(idea.time_to_implement || ''),
    expected_roi: String(idea.expected_roi || ''),
    evidence_level: Math.max(0, Math.min(2, Number(idea.evidence_level) || 0)),
    initial_stage: Number(idea.evidence_level) >= 2 ? 'Experiment' : 'Research',
    project_fit: Math.max(1, Math.min(5, Number(idea.project_fit) || 1)),
    success_metric: String(idea.success_metric || ''),
    next_action: String(idea.next_action || ''),
    score: Number(idea.score) || 0
  }));

const relevance = Number(analysis.relevance_score) || 0;
if (!ideas.length || relevance < minScore) {
  return [{ json: { ...safeMeta, skip: true, reason: String(analysis.rejection_reason || 'no_testable_candidate'), relevance } }];
}

return [{ json: {
  ...safeMeta,
  skip: false,
  relevance_score: relevance,
  summary: String(analysis.summary || ''),
  key_quotes: [],
  metrics: Array.isArray(analysis.metrics) ? analysis.metrics.map(String) : [],
  ideas,
  ideas_count: 1
} }];'''


DEDUPE_CODE = r'''const cfg = $('API Keys and Config').first().json;
const notionResponse = $('Запросить обработанные видео').first().json;
const notionResults = notionResponse.results || [];
const processedIds = new Set(notionResults.map(page => {
  try { return page.properties['Video ID'].rich_text[0].plain_text; }
  catch (e) { return null; }
}).filter(Boolean));

const maxVideos = Math.min(Number(cfg.MAX_VIDEOS || 5), 5);
const newItems = $input.all()
  .filter(item => item.json.videoId && !processedIds.has(item.json.videoId))
  .sort((a, b) => new Date(b.json.publishedAt || 0) - new Date(a.json.publishedAt || 0))
  .slice(0, maxVideos);

if (!newItems.length) {
  return [{ json: { skip: true, reason: 'no_new_videos' } }];
}

return newItems.map(item => ({ json: {
  ...item.json,
  NOTION_API_KEY: cfg.NOTION_API_KEY,
  NOTION_DATABASE_ID: cfg.NOTION_DATABASE_ID
} }));'''


def patch_workflow(workflow: dict) -> list[str]:
    changes = []
    workflow["name"] = "IdeaGen v2 — weekly research gate"
    for node in workflow["nodes"]:
        name = node["name"]
        if name == "Подготовить запрос к Claude":
            node["parameters"]["jsCode"] = ANALYSIS_CODE
            changes.append(name)
        elif name == "Парсить и фильтровать идеи":
            node["parameters"]["jsCode"] = PARSER_CODE
            changes.append(name)
        elif name == "Отфильтровать дубли и сортировать":
            node["parameters"]["jsCode"] = DEDUPE_CODE
            changes.append(name)
        elif name in {"Форматировать дайджест", "Отправить в Telegram"}:
            node["disabled"] = True
            changes.append(f"disable {name}")
        elif name == "API Keys and Config":
            assignments = node.get("parameters", {}).get("assignments", {}).get("assignments", [])
            for assignment in assignments:
                if assignment.get("name") == "MAX_VIDEOS":
                    assignment["value"] = 5
                elif assignment.get("name") == "MIN_SCORE":
                    assignment["value"] = 7
            changes.append("MAX_VIDEOS=5, MIN_SCORE=7 (Research gate)")
        elif name == "Сохранить в Notion":
            body = node.get("parameters", {}).get("body", "")
            body = body.replace("'Status':      { select:    { name: 'New' } }", "'Status':      { status:    { name: 'Not started' } }")
            node["parameters"]["body"] = body
            changes.append("Notion status mapping")

    # Telegram delivery is intentionally disconnected. Source records still go
    # to New database; candidates are reviewed manually in Ideas Pipeline during
    # the v2 experiment.
    workflow.get("connections", {}).pop("Форматировать дайджест", None)
    workflow.get("connections", {}).pop("Собрать все результаты", None)
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workflow = request("GET", f"/workflows/{WORKFLOW_ID}")
    if workflow.get("active"):
        raise RuntimeError("Refusing to patch an active workflow")

    changes = patch_workflow(workflow)
    print(f"workflow={workflow['name']} active={workflow.get('active')}")
    for change in changes:
        print(f"- {change}")

    if args.dry_run:
        print("DRY RUN: no changes written")
        return

    payload = {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow.get("settings", {}),
    }
    request("PUT", f"/workflows/{WORKFLOW_ID}", payload)
    updated = request("GET", f"/workflows/{WORKFLOW_ID}")
    assert updated.get("active") is False
    assert updated["name"] == "IdeaGen v2 — weekly research gate"
    print("APPLIED: workflow remains inactive")


if __name__ == "__main__":
    main()
