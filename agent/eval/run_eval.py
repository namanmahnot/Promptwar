"""Run the golden set and the attack set against real Gemini + BigQuery.

Usage (from agent/):
    python -m eval.run_eval                 # print summary, write eval/latest.json
    python -m eval.run_eval --save-mongo    # also insert into MongoDB `eval_runs` (needs MONGO_URI)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.evaluation import run_evaluation
from app.graph import Agent
from app.main import _production_dependencies

OUT = Path(__file__).with_name("latest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--save-mongo", action="store_true")
    args = parser.parse_args()

    deps = _production_dependencies()
    if not deps.schema.loaded:
        print("Schema did not load; check BigQuery credentials (gcloud auth application-default login).")
        return 2

    summary = run_evaluation(Agent(deps), deps, workers=args.workers)
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Execution accuracy : {summary['executionAccuracy']:.0%}  ({summary['n']} questions)")
    print(f"Valid SQL rate     : {summary['validSqlRate']:.0%}")
    print(f"Attack block rate  : {summary['attackBlockRate']:.0%}")
    print(f"Grounding issues   : {summary['groundingViolations']}")
    print(f"Latency p50 / p95  : {summary['p50Ms']} ms / {summary['p95Ms']} ms")
    print(f"Median bytes       : {summary['medianBytes']:,}")
    print(f"Mean LLM calls     : {summary['meanLlmCalls']}")
    for result in summary["results"] + summary["attacks"]:
        mark = "PASS" if result["pass"] else "FAIL"
        print(f"  {mark} {result.get('qid') or result.get('id')}: {result.get('code') or result.get('status')}")

    if args.save_mongo:
        from pymongo import MongoClient

        with MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000) as client:
            client.get_default_database("insightpilot")["eval_runs"].insert_one(dict(summary))
        print("Saved to MongoDB eval_runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
