"""Measure how well the avatar answers: accuracy, continuity, emotions, safety and latency.

Runs every case of tools/eval/eval_set.json against the real local Ollama through the
engine's own generation path (same prompt, memory, validation and emotion code the live
uses; no voice, no overlay). Development tool only, never needed to run ChatToon.

    python tools/eval_intelligence.py --model qwen3.5:2b --repeat 2 --out results.json

To measure another checkout (e.g. the code before a change), point PYTHONPATH at it:

    PYTHONPATH=/path/to/old/checkout python tools/eval_intelligence.py --label before ...

Objective cases have verifiable answers and give the accuracy figure. The other cases
are checked with the documented criteria of each check type (docs/INTELLIGENCE.md);
they are reported separately and never mixed into the accuracy percentage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
_UNITS = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
          "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_ABSTAIN = ("nao sei", "nao faco ideia", "nao tenho como saber", "nao me contou", "nao me disse", "voce nao me",
            "me conta", "me diz", "nao sei dizer", "nao consigo saber", "nao tenho essa informacao", "nao tenho acesso",
            "nao faco a menor ideia", "so voce sabe", "nao sei qual", "nao sei quanto", "conta pra mim", "como se chama",
            "qual e o nome", "nao me falou", "nao sei o nome", "ainda nao me")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def number_words(n: int) -> set[str]:
    """Portuguese spellings of small integers (enough for the evaluation set)."""
    out = {str(n)}
    if 0 <= n < 20:
        out.add(_UNITS[n])
        if n == 1:
            out.add("uma")
        if n == 2:
            out.add("duas")
        if n == 14:
            out.add("quatorze")
    elif n < 100:
        tens, unit = divmod(n, 10)
        out.add(_TENS[tens] if unit == 0 else f"{_TENS[tens]} e {_UNITS[unit]}")
    return {fold(w) for w in out}


def check(case_check: dict, text: str, emotion: str) -> bool:
    t = f" {fold(text)} "
    if "number" in case_check:
        import re
        n = case_check["number"]
        if re.search(rf"(?<![\d.,]){n}(?![\d]|[.,]\d)", text):
            return True
        return any(re.search(rf"\b{w}\b", t) for w in number_words(n) if not w.isdigit())
    if "word" in case_check:  # a short token on its own: "cd", "ls", "C", "Au"
        import re
        return any(re.search(rf"(?<![\w-]){re.escape(fold(w))}(?![\w+#-])", t) for w in case_check["word"])
    if "any" in case_check:
        return any(fold(v) in t for v in case_check["any"])
    if "none" in case_check:
        return not any(fold(v) in t for v in case_check["none"])
    if "emotion_in" in case_check:
        return emotion in case_check["emotion_in"]
    if "emotion_not" in case_check:
        return emotion not in case_check["emotion_not"]
    if "question" in case_check:
        return "?" in text
    if "abstain" in case_check:
        return any(a in t for a in _ABSTAIN) or ("?" in text and not any(c.isdigit() for c in text))
    raise ValueError(f"unknown check {case_check}")


def message(i: int, spec: dict, default_author: str = "Viewer"):
    from chattoon.core.messages import ChatMessage

    platform = spec.get("platform", "youtube")
    return ChatMessage(id=f"eval-{i}", author=spec.get("author", default_author), text=spec["text"],
                       author_id=spec.get("author_id", ""), platform=platform, source_id=f"{platform}-eval")


class Recorder:
    """Wraps the Ollama client: keeps token counts and timing of every call."""

    def __init__(self, client):
        self.client, self.calls = client, []

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def chat(self, *args, **kw):
        started = time.monotonic()
        result = await self.client.chat(*args, **kw)
        raw = result.raw or {}
        self.calls.append({"seconds": time.monotonic() - started, "prompt_tokens": raw.get("prompt_eval_count", 0),
                           "eval_tokens": raw.get("eval_count", 0), "done_reason": raw.get("done_reason", ""),
                           "temperature": kw.get("temperature")})
        return result


async def run_case(case: dict, args, counter: list[int]) -> dict:
    from chattoon.core.config import Settings
    from chattoon.core.engine import ChatToonEngine

    s = Settings(character=case.get("character", args.character), mode="auto")
    s.ai.model = args.model
    s.ai.temperature = args.temperature
    if args.no_reference and hasattr(s.ai, "reference"):
        s.ai.reference = False
    if args.no_draft and hasattr(s.ai, "fact_draft"):
        s.ai.fact_draft = False
    s.ai.reply_language = "pt-BR"
    s.context.channel_name = "BigLinux"
    s.context.topic = "Linux, software livre e jogos"
    engine = ChatToonEngine(s)
    recorder = Recorder(engine.ollama)
    engine.ollama = recorder
    commit = getattr(engine, "commit", None)  # ChatToon 3: memory keeps only what was delivered
    try:
        for spec in case.get("setup", []):
            counter[0] += 1
            reply = await engine.generate(message(counter[0], spec), announce=False)
            if reply is not None and commit:
                commit(reply)
        recorder.calls.clear()
        counter[0] += 1
        started = time.monotonic()
        reply = await engine.generate(message(counter[0], case, case.get("author", "Viewer")), announce=False)
        seconds = time.monotonic() - started
    finally:
        await engine.ollama.close()
        close = getattr(engine, "close_memory", None)
        if close:
            close()
    if reply is None:
        return {"id": case["id"], "ok": False, "text": "", "emotion": "", "error": "no reply", "seconds": seconds}
    results = [check(c, reply.text, reply.emotion) for c in case["checks"]]
    calls = recorder.calls
    return {"id": case["id"], "category": case["category"], "objective": case.get("objective", False),
            "ok": all(results), "text": reply.text, "emotion": reply.emotion, "source": reply.source,
            "seconds": round(seconds, 2), "llm_calls": len(calls),
            "prompt_tokens": sum(c["prompt_tokens"] for c in calls), "eval_tokens": sum(c["eval_tokens"] for c in calls),
            "truncated": any(c["done_reason"] == "length" for c in calls),
            "temperature": calls[-1]["temperature"] if calls else None}


def summarize(rows: list[dict], label: str) -> dict:
    objective = [r for r in rows if r.get("objective")]
    other = [r for r in rows if not r.get("objective")]
    per_cat: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        per_cat[r.get("category", "?")].append(r["ok"])
    seconds = sorted(r["seconds"] for r in rows if r.get("llm_calls", 1))
    prompt = [r["prompt_tokens"] for r in rows if r.get("prompt_tokens")]
    return {
        "label": label,
        "objective_accuracy": round(100 * sum(r["ok"] for r in objective) / max(1, len(objective)), 1),
        "objective_cases": len(objective),
        "criteria_pass_rate": round(100 * sum(r["ok"] for r in other) / max(1, len(other)), 1),
        "criteria_cases": len(other),
        "per_category": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(per_cat.items())},
        "emotions": dict(Counter(r["emotion"] for r in rows).most_common()),
        "latency_p50": round(statistics.median(seconds), 2) if seconds else 0,
        "latency_p95": round(seconds[int(0.95 * (len(seconds) - 1))], 2) if seconds else 0,
        "avg_prompt_tokens": round(statistics.mean(prompt)) if prompt else 0,
        "truncated": sum(1 for r in rows if r.get("truncated")),
        "fallbacks": sum(1 for r in rows if r.get("source") == "fallback"),
        "llm_calls": sum(r.get("llm_calls", 0) for r in rows),
    }


def rescore(path: str) -> int:
    """Apply the current checks to saved replies (used after fixing a checker bug, so every
    run — before and after — is scored by the same rules)."""
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = {}
    for name in ("eval", "holdout", "holdout2"):
        for c in json.loads((HERE / "eval" / f"{name}_set.json").read_text(encoding="utf-8"))["cases"]:
            cases[c["id"]] = c
    for row in saved["rows"]:
        case = cases.get(row["id"])
        if case and row.get("text") is not None:
            row["ok"] = all(check(c, row["text"], row.get("emotion", "")) for c in case["checks"])
    saved["summary"] = summarize(saved["rows"], saved["summary"]["label"])
    Path(path).write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(saved["summary"], ensure_ascii=False, indent=2))
    return 0


async def main_async(args) -> int:
    data = json.loads((HERE / "eval" / f"{args.set}_set.json").read_text(encoding="utf-8"))
    cases = [c for c in data["cases"] if not args.only or any(c["id"].startswith(p) for p in args.only.split(","))]
    rows, counter = [], [0]
    for rep in range(args.repeat):
        for case in cases:
            row = await run_case(case, args, counter)
            row["repeat"] = rep
            rows.append(row)
            mark = "✔" if row["ok"] else "✘"
            print(f"{mark} {row['id']:<9} {row.get('emotion', ''):<10} {row['seconds']:>5.2f}s  {row['text'][:110]}",
                  flush=True)
    summary = summarize(rows, args.label)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "model": args.model, "temperature": args.temperature,
                                              "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="qwen3.5:2b")
    p.add_argument("--character", default="tux")
    p.add_argument("--temperature", type=float, default=0.9, help="the streamer's creativity setting")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--only", default="", help="comma separated id prefixes (e.g. math,cont)")
    p.add_argument("--label", default="current")
    p.add_argument("--set", default="eval", choices=["eval", "holdout", "holdout2"], help="eval (main) or holdout (never tuned on)")
    p.add_argument("--out", default="")
    p.add_argument("--no-reference", action="store_true", help="ablation: without the verified reference sheet")
    p.add_argument("--no-draft", action="store_true",
                   help="for snapshots that still had the (rejected) factual draft step: switch it off")
    p.add_argument("--objective-temp", type=float, default=None, help="experiment: temperature of objective questions")
    p.add_argument("--rescore", default="", help="recompute the checks of a saved results file (no model calls)")
    args = p.parse_args()
    # memories of the evaluation never reach the real ~/.local/share
    tmp = tempfile.mkdtemp(prefix="chattoon-eval-")
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        os.environ[var] = os.path.join(tmp, var.lower())
    os.environ["CHATTOON_CREDENTIALS"] = "memory"
    sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(os.pathsep)[0] or str(HERE.parent))
    if args.rescore:
        return rescore(args.rescore)
    if args.objective_temp is not None:
        import chattoon.core.intent as intent_module
        if hasattr(intent_module, "OBJECTIVE_TEMPERATURE"):
            intent_module.OBJECTIVE_TEMPERATURE = args.objective_temp
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
