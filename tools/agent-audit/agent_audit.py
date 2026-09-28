#!/usr/bin/env python3
"""Аудит скиллов Claude, launchd-агентов и Python-скриптов на Mac.

Только чтение. Содержимое скриптов и секреты в отчёт не попадают — только
метаданные (пути, даты, размеры, кто кого вызывает, какая модель Claude).

Запуск:
    python3 agent_audit.py                       # сканирует $HOME
    python3 agent_audit.py --roots ~/b360 ~/scripts
    python3 agent_audit.py --stale-days 30

Результат: ~/agent-audit/audit-YYYY-MM-DD.md и .json
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
NOW = dt.datetime.now(dt.timezone.utc)

SKIP_DIRS = {
    "Library", ".Trash", "node_modules", ".venv", "venv", "env", ".env",
    "site-packages", "__pycache__", ".git", ".cache", "Applications",
    "Pictures", "Movies", "Music", ".npm", ".pyenv", ".rbenv", "anaconda3",
    "miniconda3", ".cargo", ".rustup", ".gradle", ".m2", "dist", "build",
    ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode", "Downloads",
}

BUILTIN_COMMANDS = {
    "model", "clear", "compact", "help", "config", "login", "logout", "cost",
    "status", "memory", "init", "resume", "exit", "permissions", "mcp",
    "agents", "hooks", "doctor", "bug", "vim", "terminal-setup", "add-dir",
    "export", "context", "rewind", "usage", "statusline", "ide", "fast",
    "plan", "release-notes", "upgrade", "privacy-settings", "theme",
    "output-style", "todos", "tasks", "bashes", "feedback", "pr-comments",
    "install-github-app", "migrate-installer", "loop", "effort",
}

MODEL_PATTERNS = [
    re.compile(r"\bclaude-(?:opus|sonnet|haiku|fable)[a-z0-9.\-]*", re.I),
    re.compile(r"--model[ =]+['\"]?([a-z][a-z0-9.\-]+)", re.I),
    re.compile(r"\b(?:opus|sonnet|haiku|fable)-\d[\d.\-]*\b", re.I),
]


def extract_models(text):
    found = set()
    for pat in MODEL_PATTERNS:
        for m in pat.finditer(text):
            found.add((m.group(1) if m.groups() else m.group(0)).lower().rstrip(".-"))
    return sorted(found)


def iso(ts):
    return ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else "—"


def mtime(p):
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(p), dt.timezone.utc)
    except OSError:
        return None


def days_ago(ts):
    return None if ts is None else (NOW - ts).days


# ---------------------------------------------------------------- skills
def find_skills():
    """Все SKILL.md: личные, плагинные, проектные (.claude/skills в репо)."""
    found = {}
    roots = [HOME / ".claude" / "skills", HOME / ".claude" / "plugins"]
    for root in roots:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            name = skill_md.parent.name
            found.setdefault(name, []).append(skill_md)
    return found


def add_project_skills(found, scan_roots):
    for root in scan_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS or d == ".claude"]
            if dirpath.endswith(os.path.join(".claude", "skills")):
                for d in dirnames:
                    md = Path(dirpath) / d / "SKILL.md"
                    if md.exists():
                        found.setdefault(d, []).append(md)


def skill_usage():
    """Вызовы скиллов из журналов Claude Code (~/.claude/projects/**/*.jsonl)."""
    uses = collections.defaultdict(list)  # name -> [(ts, project)]
    base = HOME / ".claude" / "projects"
    if not base.exists():
        return uses, 0
    n_files = 0
    cmd_re = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
    for jf in base.rglob("*.jsonl"):
        n_files += 1
        project = jf.parent.name
        try:
            fh = open(jf, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"Skill"' not in line and "<command-name>" not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                ts = o.get("timestamp")
                try:
                    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
                except ValueError:
                    t = None
                content = (o.get("message") or {}).get("content")
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                            s = str((b.get("input") or {}).get("skill", "")).strip()
                            if s:
                                uses[s].append((t, project))
                elif isinstance(content, str):
                    for m in cmd_re.finditer(content):
                        s = m.group(1)
                        if s.split(":")[-1] not in BUILTIN_COMMANDS:
                            uses[s].append((t, project))
    return uses, n_files


def skills_report(scan_roots):
    found = find_skills()
    add_project_skills(found, scan_roots)
    uses, n_files = skill_usage()

    def uses_for(name):
        out = []
        for k, v in uses.items():
            if k == name or k.split(":")[-1] == name:
                out.extend(v)
        return out

    rows = []
    for name, paths in sorted(found.items()):
        u = uses_for(name)
        stamps = [t for t, _ in u if t]
        last = max(stamps) if stamps else None
        rows.append({
            "name": name,
            "paths": [str(p) for p in paths],
            "edited": iso(max(filter(None, (mtime(p) for p in paths)), default=None)),
            "uses_total": len(u),
            "uses_30d": sum(1 for t in stamps if (NOW - t).days <= 30),
            "uses_90d": sum(1 for t in stamps if (NOW - t).days <= 90),
            "last_used": iso(last),
            "last_used_days": days_ago(last),
            "projects": sorted({p for _, p in u})[:5],
        })
    known = {r["name"] for r in rows}
    unknown = []
    for k, v in uses.items():
        if k.split(":")[-1] not in known:
            stamps = [t for t, _ in v if t]
            unknown.append({"name": k, "uses_total": len(v),
                            "last_used": iso(max(stamps) if stamps else None)})
    return rows, sorted(unknown, key=lambda r: -r["uses_total"]), n_files


# ---------------------------------------------------------------- launchd
def launchctl_status():
    """None — launchctl недоступен (не Mac), иначе {label: {...}}."""
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    st = {}
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            pid, code, label = parts
            st[label] = {"pid": None if pid == "-" else pid, "last_exit": code}
    return st


def schedule_text(p):
    if "StartCalendarInterval" in p:
        cal = p["StartCalendarInterval"]
        cal = cal if isinstance(cal, list) else [cal]
        parts = []
        for c in cal:
            wd = c.get("Weekday")
            hh, mm = c.get("Hour"), c.get("Minute", 0)
            s = f"{hh:02d}:{mm:02d}" if hh is not None else f"каждый час :{mm:02d}"
            if wd is not None:
                s = f"wd{wd} {s}"
            if c.get("Day") is not None:
                s = f"день {c['Day']} {s}"
            parts.append(s)
        return "cal " + ", ".join(parts[:4]) + (" …" if len(parts) > 4 else "")
    if "StartInterval" in p:
        return f"каждые {p['StartInterval']//60} мин"
    if p.get("KeepAlive"):
        return "KeepAlive (демон)"
    if p.get("RunAtLoad"):
        return "при загрузке"
    return "—"


def launchd_report():
    agents = []
    st = launchctl_status()
    have_launchctl = st is not None
    st = st or {}
    for d in [HOME / "Library" / "LaunchAgents"]:
        if not d.exists():
            continue
        for plist in sorted(d.glob("*.plist")):
            try:
                with open(plist, "rb") as fh:
                    p = plistlib.load(fh)
            except Exception as e:  # битый plist — это тоже находка
                agents.append({"label": plist.stem, "plist": str(plist), "error": f"plist не читается: {e}"})
                continue
            label = p.get("Label", plist.stem)
            args = p.get("ProgramArguments") or ([p["Program"]] if p.get("Program") else [])
            joined = " ".join(map(str, args))
            scripts = [a for a in args if str(a).endswith((".py", ".sh"))]
            logs = [p.get("StandardOutPath"), p.get("StandardErrorPath")]
            log_ts = max(filter(None, (mtime(l) for l in logs if l)), default=None)
            missing = [s for s in scripts if not Path(os.path.expanduser(s)).exists()]
            # модель — из самой команды и из вызываемых скриптов
            model_src = joined
            for sc in scripts:
                try:
                    model_src += "\n" + Path(os.path.expanduser(sc)).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
            models = extract_models(model_src)
            s = st.get(label, {})
            agents.append({
                "label": label,
                "plist": str(plist),
                "loaded": (label in st) if have_launchctl else None,
                "running_pid": s.get("pid"),
                "last_exit": s.get("last_exit"),
                "schedule": schedule_text(p),
                "disabled": bool(p.get("Disabled")),
                "scripts": scripts,
                "missing_scripts": missing,
                "command": joined[:200],
                "models": models,
                "last_log_write": iso(log_ts),
                "last_log_days": days_ago(log_ts),
            })
    return agents


# ---------------------------------------------------------------- python
def find_py(scan_roots):
    for root in scan_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for f in filenames:
                if f.endswith(".py"):
                    yield Path(dirpath) / f


def git_root(p):
    for parent in [p.parent, *p.parents]:
        if (parent / ".git").exists():
            return parent
        if parent == HOME:
            break
    return None


def python_report(scan_roots, agents, stale_days):
    ref = collections.defaultdict(list)
    for a in agents:
        for s in a.get("scripts", []):
            ref[str(Path(os.path.expanduser(s)).resolve())].append(a["label"])
    rows, hashes = [], collections.defaultdict(list)
    for py in find_py(scan_roots):
        try:
            raw = py.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", errors="replace")
        h = hashlib.sha1(raw).hexdigest()[:12]
        rp = str(py.resolve())
        hashes[h].append(rp)
        m = mtime(py)
        labels = ref.get(rp, [])
        is_entry = "__main__" in text
        gr = git_root(py)
        models = extract_models(text)[:6]
        uses_claude = ("claude" in text and "-p" in text) or "anthropic" in text
        if labels:
            status = "scheduled"
        elif not is_entry:
            status = "module"  # импортируемый модуль/хелпер
        elif days_ago(m) is not None and days_ago(m) > stale_days:
            status = "orphan"
        else:
            status = "manual"  # точка входа, не в расписании, трогали недавно
        rows.append({
            "path": rp.replace(str(HOME), "~"),
            "lines": text.count("\n") + 1,
            "modified": iso(m),
            "modified_days": days_ago(m),
            "git_repo": str(gr).replace(str(HOME), "~") if gr else None,
            "launchd": labels,
            "entrypoint": is_entry,
            "uses_claude": uses_claude,
            "models": models,
            "status": status,
            "sha1": h,
        })
    dups = [v for v in hashes.values() if len(v) > 1]
    return rows, dups


# ---------------------------------------------------------------- output
def md_table(rows, cols):
    head = "| " + " | ".join(c[1] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for r in rows:
        cells = []
        for key, _ in cols:
            v = r.get(key)
            if isinstance(v, list):
                v = ", ".join(map(str, v)) or "—"
            cells.append(str(v if v not in (None, "") else "—").replace("|", "\\|"))
        body += "| " + " | ".join(cells) + " |\n"
    return head + body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="*", default=[str(HOME)])
    ap.add_argument("--stale-days", type=int, default=60)
    ap.add_argument("--out", default=str(HOME / "agent-audit"))
    a = ap.parse_args()
    roots = [Path(os.path.expanduser(r)) for r in a.roots]

    print("→ скиллы…", file=sys.stderr)
    skills, unknown_skills, n_logs = skills_report(roots)
    print("→ launchd…", file=sys.stderr)
    agents = launchd_report()
    print("→ python…", file=sys.stderr)
    scripts, dups = python_report(roots, agents, a.stale_days)

    # аномалии
    issues = []
    for ag in agents:
        if ag.get("error"):
            issues.append(f"🔴 `{ag['label']}` — {ag['error']}")
        if ag.get("missing_scripts"):
            issues.append(f"🔴 `{ag['label']}` вызывает несуществующий файл: {', '.join(ag['missing_scripts'])}")
        if ag.get("last_exit") not in (None, "0", "-"):
            issues.append(f"🟠 `{ag['label']}` — последний код выхода {ag['last_exit']}")
        if ag.get("last_log_days") is not None and ag["last_log_days"] > 7 and not ag.get("disabled"):
            issues.append(f"🟡 `{ag['label']}` — лог не обновлялся {ag['last_log_days']} дн. (агент молчит?)")
        if ag.get("loaded") is False and not ag.get("disabled") and not ag.get("error"):
            issues.append(f"🟡 `{ag['label']}` — plist лежит, но в launchctl не загружен")
    for s in skills:
        if s["uses_total"] == 0:
            issues.append(f"⚪ скилл `{s['name']}` — ни одного вызова в журналах")
    for d in dups:
        issues.append("🟡 дубль скрипта: " + " = ".join(p.replace(str(HOME), "~") for p in d))

    by_status = collections.Counter(s["status"] for s in scripts)
    date = NOW.strftime("%Y-%m-%d")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    md = [f"# Аудит агентов, скиллов и скриптов — {date}\n",
          f"Корни сканирования: {', '.join(str(r) for r in roots)}  ",
          f"Журналов Claude просмотрено: {n_logs}\n",
          "## Сводка",
          f"- Скиллов: **{len(skills)}** (без вызовов: {sum(1 for s in skills if s['uses_total']==0)}, "
          f"не вызывались >90 дн.: {sum(1 for s in skills if s['uses_total'] and (s['last_used_days'] or 0) > 90)})",
          f"- launchd-агентов: **{len(agents)}** (загружено: {sum(1 for x in agents if x.get('loaded'))}, "
          f"с ошибкой выхода: {sum(1 for x in agents if x.get('last_exit') not in (None,'0','-'))})",
          f"- Python-скриптов: **{len(scripts)}** — " + ", ".join(f"{k}: {v}" for k, v in by_status.most_common()),
          f"- Дублей: {len(dups)}\n",
          "## ⚠️ Аномалии", *(issues or ["Нет"]), "",
          "## Скиллы",
          md_table(sorted(skills, key=lambda r: (r["last_used_days"] is None, r["last_used_days"] or 0)),
                   [("name", "Скилл"), ("last_used", "Посл. вызов"), ("uses_30d", "30д"), ("uses_90d", "90д"),
                    ("uses_total", "Всего"), ("edited", "Правили"), ("projects", "Где вызывали")]),
          "### Вызовы скиллов, которых нет на диске (облачные/плагинные/удалённые)",
          md_table(unknown_skills, [("name", "Имя"), ("uses_total", "Всего"), ("last_used", "Посл. вызов")]) if unknown_skills else "Нет\n",
          "## launchd-агенты",
          md_table(sorted(({**x, "scripts": [str(s).replace(str(HOME), "~") for s in x.get("scripts", [])]}
                           for x in agents), key=lambda r: r["label"]),
                   [("label", "Label"), ("schedule", "Расписание"), ("loaded", "Загружен"), ("last_exit", "Exit"),
                    ("last_log_write", "Посл. лог"), ("scripts", "Скрипт"), ("models", "Модель")]),
          "## Python-скрипты"]
    for st in ["scheduled", "manual", "module", "orphan"]:
        grp = [s for s in scripts if s["status"] == st]
        if not grp:
            continue
        title = {"scheduled": "В расписании launchd", "manual": "Точки входа вне расписания (запускаются руками?)",
                 "module": "Модули/хелперы", "orphan": f"Сироты (не в расписании, не трогали >{a.stale_days} дн.)"}[st]
        md.append(f"### {title} — {len(grp)}")
        md.append(md_table(sorted(grp, key=lambda r: r["path"]),
                           [("path", "Путь"), ("modified", "Изменён"), ("lines", "Строк"), ("launchd", "Агент"),
                            ("uses_claude", "Claude"), ("models", "Модель"), ("git_repo", "Git")]))

    (out / f"audit-{date}.md").write_text("\n".join(md), encoding="utf-8")
    (out / f"audit-{date}.json").write_text(json.dumps(
        {"date": date, "roots": [str(r) for r in roots], "skills": skills, "unknown_skills": unknown_skills,
         "agents": agents, "scripts": scripts, "duplicates": dups, "issues": issues},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Готово: {out}/audit-{date}.md")
    print(f"   скиллов {len(skills)} · агентов {len(agents)} · скриптов {len(scripts)} · аномалий {len(issues)}")


if __name__ == "__main__":
    main()
