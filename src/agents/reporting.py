"""Execution reporting and results saving utilities."""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.notifications.telegram import TelegramNotifier


def save_results(agent_name: str, results: dict[str, Any]) -> None:
    output_dir = Path.cwd() / "results"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"{agent_name}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to {filename}")


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def send_execution_report(telegram: TelegramNotifier, agent_name: str, results: dict[str, Any]) -> None:
    if agent_name == "pr-assistant":
        return

    esc = telegram.escape_html
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    metrics: dict[str, Any] = results.get("_metrics", {})
    duration_s = metrics.get("duration_seconds")
    duration_str = _format_duration(duration_s) if duration_s is not None else "\u2014"
    success_rate = metrics.get("success_rate")

    lines = [
        "\U0001f916 <b>GITHUB ASSISTANCE REPORT</b>",
        f"\U0001f4c5 <code>{esc(now)}</code>",
        f"\U0001f464 <b>Agente:</b> <code>{esc(agent_name.replace('-', ' ').upper())}</code>",
        f"\u23f1\ufe0f <b>Dura\u00e7\u00e3o:</b> <code>{esc(duration_str)}</code>",
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
    ]
    if success_rate is not None:
        lines.append(f"\U0001f4ca <b>Taxa de sucesso:</b> <code>{success_rate:.0f}%</code>")

    if agent_name == "all":
        success_count = 0
        fail_count = 0
        for name, res in results.items():
            if "error" in res:
                fail_count += 1
                err_msg = str(res['error']).split("\n")[0][:100]
                lines.append(f"\u274c *{esc(name)}*")
                lines.append(f"  \u2514 \u26a0\ufe0f `{esc(err_msg)}`")
            else:
                success_count += 1
                lines.append(f"\u2705 *{esc(name)}*")

        lines.append("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        lines.append(f"\U0001f4ca <b>Resumo:</b> \u2705 <code>{success_count}</code> | \u274c <code>{fail_count}</code>")
    else:
        if "error" in results:
            lines.append("\U0001f4a5 <b>STATUS: FALHA CR\u00cdTICA</b>")
            err_msg = str(results['error']).split("\n")[0][:250]
            lines.append(f"\u26a0\ufe0f <b>Erro:</b> <code>{esc(err_msg)}</code>")
        else:
            lines.append("\U0001f680 <b>STATUS: OPERA\u00c7\u00c3O CONCLU\u00cdDA</b>")

            processed = results.get("processed", results.get("merged", results.get("resolved", [])))
            failed = results.get("failed", [])

            if agent_name == "senior-developer":
                sec = len(results.get("security_tasks", []))
                cicd = len(results.get("cicd_tasks", []))
                feat = len(results.get("feature_tasks", []))
                debt = len(results.get("tech_debt_tasks", []))
                if any([sec, cicd, feat, debt]):
                    lines.append("\n\U0001f6e0\ufe0f <b>Tarefas Criadas:</b>")
                    if sec: lines.append(f"  \U0001f6e1\ufe0f Seguran\u00e7a: <b>{sec}</b>")
                    if cicd: lines.append(f"  \u2699\ufe0f CI/CD: <b>{cicd}</b>")
                    if feat: lines.append(f"  \u2728 Features: <b>{feat}</b>")
                    if debt: lines.append(f"  \U0001f9f9 D\u00e9bito T\u00e9cnico: <b>{debt}</b>")

            if isinstance(processed, (list, dict)) and len(processed) > 0:
                lines.append(f"\n\U0001f4c8 <b>Itens Processados:</b> <code>{len(processed)}</code>")
            elif isinstance(processed, (int, float)) and processed > 0:
                lines.append(f"\n\U0001f4c8 <b>Itens Processados:</b> <code>{processed}</code>")

            if isinstance(failed, (list, dict)) and len(failed) > 0:
                lines.append(f"\u274c <b>Falhas:</b> <code>{len(failed)}</code>")
                for f in failed[:3]:
                    repo = f.get("repository", "unknown")
                    err = str(f.get("error", "unknown")).split("\n")[0][:50]
                    lines.append(f"  \u2514 <code>{esc(repo)}</code>: <i>{esc(err)}</i>")

    telegram.send_message("\n".join(lines), parse_mode="HTML")
