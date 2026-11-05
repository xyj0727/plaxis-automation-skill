"""Search authored textbook page notes and topic guides.

No PLAXIS connection or third-party Python packages are required.
"""
import argparse
import json
import sys
from pathlib import Path


def load_pages(path):
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            record = json.loads(line)
            if not isinstance(record.get("pdf_page"), int):
                raise ValueError("Invalid pdf_page on ledger line {}".format(number))
            records.append(record)
    return records


def search_guides(base, query):
    hits = []
    for path in sorted(base.glob("*.md"), key=lambda p: (p.name == "index.md", p.name)):
        heading = ""
        excerpts = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("#"):
                heading = line.lstrip("# ")
            if query.casefold() in line.casefold():
                excerpts.append({"line": number, "heading": heading, "text": line})
        if excerpts:
            hits.append({"file": "references/book/" + path.name, "matching_lines": len(excerpts), "excerpts": excerpts[:3]})
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="", help="Case-insensitive substring, Chinese or English")
    parser.add_argument("--page", type=int, help="One-based PDF page number (not printed page)")
    parser.add_argument("--limit", type=int, default=12, help="Maximum records shown per result category")
    parser.add_argument("--check", action="store_true", help="Validate continuous page coverage")
    parser.add_argument("--json", action="store_true", help="Output full matching records as JSON")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    base = Path(__file__).resolve().parents[1] / "references" / "book"
    pages = load_pages(base / "page-ledger.jsonl")
    if args.check:
        manifest = json.loads((base / "source-manifest.json").read_text(encoding="utf-8"))
        expected = set(range(1, manifest["page_count"] + 1))
        numbers = [p["pdf_page"] for p in pages]
        actual = set(numbers)
        invalid = [p["pdf_page"] for p in pages if not p.get("visual_reviewed") or not p.get("knowledge")]
        report = {"expected": len(expected), "records": len(pages), "missing": sorted(expected - actual), "unexpected": sorted(actual - expected), "duplicates": len(numbers) - len(actual), "unreviewed_or_empty": invalid}
        report["ok"] = not any([report["missing"], report["unexpected"], report["duplicates"], invalid])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    if args.page is None and not args.query:
        parser.error("provide a query, --page, or --check")
    matches = [p for p in pages if (args.page is None or p["pdf_page"] == args.page) and (not args.query or args.query.casefold() in json.dumps(p, ensure_ascii=False).casefold())]
    shown = matches[:args.limit]
    guides = search_guides(base, args.query) if args.query and args.page is None else []
    if args.json:
        print(json.dumps({"total_matches": len(matches) + len(guides), "page_matches": len(matches), "guide_matches": len(guides), "shown": shown, "guide_hits": guides[:args.limit]}, ensure_ascii=False, indent=2))
    else:
        for p in shown:
            print("PDF {} | printed {} | {}".format(p["pdf_page"], p.get("printed_page"), "; ".join(p.get("topics", []))))
            values = p["knowledge"] if isinstance(p["knowledge"], list) else [p["knowledge"]]
            for value in values:
                print("  - " + value)
            for value in p.get("uncertainties", []):
                print("  ? " + value)
            print()
        for guide in guides[:args.limit]:
            print(guide["file"])
            for excerpt in guide["excerpts"]:
                print("  line {} | {} | {}".format(excerpt["line"], excerpt["heading"], excerpt["text"]))
            print()
        print("{} page matches; {} guide matches. --page uses PDF page numbers.".format(len(matches), len(guides)))
    return 0 if matches or guides else 1


if __name__ == "__main__":
    sys.exit(main())
