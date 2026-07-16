#!/usr/bin/env python3
"""Add atomic Ideas Pipeline writes to the inactive IdeaGen workflow."""

import argparse
import json
import ssl
import urllib.request
from pathlib import Path


WORKFLOW_ID = "yq3FunHR5eitjZSO"
BASE_URL = "https://melnikov.app.n8n.cloud/api/v1"
PIPELINE_DATABASE_ID = "a7504f669fd04a6eaa310f4e1d153720"
ENV_FILE = Path.home() / "Developer" / "b360" / ".b360.env"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def api_key():
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("N8N_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("N8N_API_KEY not found")


def request(method, path, body=None):
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


BUILD_CODE = r'''const analysis = $('Парсить и фильтровать идеи').item.json;
const sourcePage = $json;
const idea = Array.isArray(analysis.ideas) ? analysis.ideas[0] : null;
if (!idea || !sourcePage.id) return [{json:{skip:true, reason:'missing_idea_or_source'}}];

const evidence = Math.max(0, Math.min(2, Number(idea.evidence_level) || 0));
const score = Number(idea.score) || 0;
const projectFit = Math.max(1, Math.min(5, Number(idea.project_fit) || 1));
const difficulty = String(idea.difficulty || 'medium').toLowerCase();
const effort = difficulty.includes('low') ? 1 : difficulty.includes('high') ? 4 : 2;
const risk = difficulty.includes('high') ? 'High' : difficulty.includes('low') ? 'Low' : 'Medium';
const stage = evidence >= 2 && score >= 8 ? 'Experiment' : 'Research';
const categoryMap = {
  'Automation':'Automation', 'Product':'Product', 'AI development':'AI development',
  'Knowledge':'Knowledge', 'Marketing':'Marketing', 'Content':'Marketing',
  'Operations':'Automation', 'Data':'Automation', 'Growth':'Marketing',
  'Monetization':'Product'
};
const theme = categoryMap[String(idea.category || '')] || 'AI development';
const review = new Date(Date.now() + 7 * 86400000).toISOString().slice(0,10);
const tr = (value, limit) => String(value || '').slice(0, limit);
const bodyText = [
  'Hypothesis: ' + String(idea.description || ''),
  'Verification plan: ' + (Array.isArray(idea.implementation) ? idea.implementation.join('; ') : ''),
  'Tools: ' + (Array.isArray(idea.tools) ? idea.tools.join(', ') : ''),
  'ROI: ' + String(idea.expected_roi || 'Not verified; baseline required.'),
  'Source: ' + String(analysis.videoUrl || '')
].join('\n\n');
const pipelinePayload = {
  parent:{database_id:'__PIPELINE_DATABASE_ID__'},
  properties:{
    'Idea':{title:[{text:{content:tr(idea.title,200)}}]},
    'Stage':{select:{name:stage}},
    'Theme':{multi_select:[{name:theme}]},
    'Evidence':{number:evidence},
    'Value':{number:Math.max(1, Math.min(5, score - 4))},
    'Project fit':{number:projectFit},
    'Effort':{number:effort},
    'Risk':{select:{name:risk}},
    'Score':{number:score},
    'Next action':{rich_text:[{text:{content:tr(idea.next_action,1900)}}]},
    'Success metric':{rich_text:[{text:{content:tr(idea.success_metric,1900)}}]},
    'Decision reason':{rich_text:[{text:{content:tr(`IdeaGen v2: relevance ${analysis.relevance_score || 0}/10; source claim requires ${stage === 'Research' ? 'verification' : 'experiment'}.`,1900)}}]},
    'Review date':{date:{start:review}},
    'Source':{relation:[{id:sourcePage.id}]}
  },
  children:[{object:'block',type:'paragraph',paragraph:{rich_text:[{type:'text',text:{content:tr(bodyText,1900)}}]}}]
};

return [{json:{
  skip:false,
  source_page_id:sourcePage.id,
  source_url:analysis.videoUrl || '',
  title:String(idea.title || '').slice(0,200),
  stage, theme, evidence,
  value:Math.max(1, Math.min(5, score - 4)),
  project_fit:projectFit,
  effort, risk, score,
  next_action:String(idea.next_action || ''),
  success_metric:String(idea.success_metric || ''),
  decision_reason:`IdeaGen v2: relevance ${analysis.relevance_score || 0}/10; source claim requires ${stage === 'Research' ? 'verification' : 'experiment'}.`,
  review_date:review,
  description:String(idea.description || ''),
  implementation:Array.isArray(idea.implementation) ? idea.implementation : [],
  tools:Array.isArray(idea.tools) ? idea.tools : [],
  expected_roi:String(idea.expected_roi || ''),
  pipeline_body:JSON.stringify(pipelinePayload)
}}];'''

BUILD_CODE = BUILD_CODE.replace("__PIPELINE_DATABASE_ID__", PIPELINE_DATABASE_ID)


PIPELINE_BODY = "={{ $json.pipeline_body }}"


def http_node(name, position, body):
    return {
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "parameters": {
            "method": "POST",
            "url": "https://api.notion.com/v1/pages",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Authorization", "value": "={{ 'Bearer ' + $('API Keys and Config').first().json.NOTION_API_KEY }}"},
                {"name": "Notion-Version", "value": "2022-06-28"},
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True,
            "contentType": "raw",
            "rawContentType": "application/json",
            "body": body,
            "options": {},
        },
    }


def patch(workflow):
    names = {node["name"] for node in workflow["nodes"]}
    if "Подготовить карточку Pipeline" not in names:
        workflow["nodes"].append({
            "name": "Подготовить карточку Pipeline",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1700, 100],
            "parameters": {"jsCode": BUILD_CODE},
        })
    else:
        next(node for node in workflow["nodes"] if node["name"] == "Подготовить карточку Pipeline")["parameters"]["jsCode"] = BUILD_CODE

    if "Сохранить в Ideas Pipeline" not in names:
        workflow["nodes"].append(http_node("Сохранить в Ideas Pipeline", [1940, 100], PIPELINE_BODY))
    else:
        next(node for node in workflow["nodes"] if node["name"] == "Сохранить в Ideas Pipeline")["parameters"]["body"] = PIPELINE_BODY

    source = next(node for node in workflow["nodes"] if node["name"] == "Сохранить в Notion")
    body = source["parameters"]["body"]
    body = body.replace("'Status':      { status:    { name: 'Not started' } }", "'Status':      { status:    { name: 'Done' } }")
    marker = "'Ideas_count': { number: Number($json.ideas_count) || 0 }"
    replacement = marker + ",\n      'Record type': { select: { name: 'Source' } },\n      'Processed':   { checkbox: true },\n      'Disposition': { select: { name: 'Promote' } }"
    if "'Record type'" not in body:
        body = body.replace(marker, replacement)
    source["parameters"]["body"] = body

    workflow["connections"]["Есть ценные идеи"] = {
        "main": [[{"node": "Сохранить в Notion", "type": "main", "index": 0}], []]
    }
    workflow["connections"]["Сохранить в Notion"] = {
        "main": [[{"node": "Подготовить карточку Pipeline", "type": "main", "index": 0}]]
    }
    workflow["connections"]["Подготовить карточку Pipeline"] = {
        "main": [[{"node": "Сохранить в Ideas Pipeline", "type": "main", "index": 0}]]
    }
    workflow["connections"].pop("Сохранить в Ideas Pipeline", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    workflow = request("GET", f"/workflows/{WORKFLOW_ID}")
    if workflow.get("active"):
        raise RuntimeError("Refusing to patch active workflow")
    patch(workflow)
    print("nodes:", len(workflow["nodes"]))
    print("chain: Есть ценные идеи -> Сохранить в Notion -> Подготовить карточку Pipeline -> Сохранить в Ideas Pipeline")
    if args.dry_run:
        print("DRY RUN")
        return
    payload = {k: workflow[k] for k in ["name", "nodes", "connections", "settings"]}
    request("PUT", f"/workflows/{WORKFLOW_ID}", payload)
    updated = request("GET", f"/workflows/{WORKFLOW_ID}")
    assert updated.get("active") is False
    assert any(n["name"] == "Сохранить в Ideas Pipeline" for n in updated["nodes"])
    print("APPLIED: workflow remains inactive")


if __name__ == "__main__":
    main()
