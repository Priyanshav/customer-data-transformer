"""CLI entry point.

Examples:
  python main.py --inputs samples
  python main.py --csv samples/recruiter.csv --ats-json samples/ats.json \
                 --resume samples/resume.txt --config configs/custom_config.json
"""
from __future__ import annotations
import argparse
import json
import sys
from engine.ingest import load_sources_from_args
from engine.pipeline import Pipeline

def main(argv=None):
    parser = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    parser.add_argument("--csv")
    parser.add_argument("--ats-json", dest="ats_json")
    parser.add_argument("--resume", help="resume .pdf or .txt")
    parser.add_argument("--inputs", help="folder; auto-detects files by extension")
    parser.add_argument("--config", help="runtime output config JSON")
    parser.add_argument("--out", help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    sources = load_sources_from_args(args)
    if not sources:
        parser.error("provide at least one of --csv / --ats-json / --resume / --inputs")

    config = None
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)

    result = Pipeline().run(sources, config)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0

if __name__ == "__main__":
    sys.exit(main())
