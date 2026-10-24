"""Merge genuine human semantic judgments without silently dropping pending rows.

Usage: python -m p6_evaluation.practice.review <evaluation-directory>
Edit that run's human_review.json first. This never calls an LLM judge.
"""
import argparse
from pathlib import Path

from practice_common.runtime import load_json, load_jsonl, save_json
from .solution import summarize


def apply_reviews(root):
    root = Path(root)
    results = load_jsonl(root / 'results.jsonl')
    reviews = load_json(root / 'human_review.json')
    key = lambda r: (r['variant'], r['case_id'], r['trial'])
    indexed = {key(r): r for r in reviews}
    if len(indexed) != len(reviews) or set(indexed) != {key(r) for r in results}:
        raise ValueError('reviews must cover exactly the original result rows')
    reviewed, pending = [], 0
    for row in results:
        review = indexed[key(row)]
        if review['answer'] != row['actual']['answer'] or review['trace_path'] != row['trace_path']:
            raise ValueError('review does not match the original answer/trace')
        decision = review.get('semantic_correct')
        if decision is None:
            pending += 1
            continue
        if type(decision) is not bool or not str(review.get('reviewer') or '').strip():
            raise ValueError('review requires boolean semantic_correct and named reviewer')
        # A human may assess paraphrase entailment, but cannot override database,
        # provenance, confirmation, schema, budget or required-fact failures.
        mechanical = all(ok for name, ok in row['checks'].items() if name != 'citation_support')
        reviewed.append(dict(row, success=mechanical and decision, semantic_review='human_reviewed'))
    output = {'total_runs': len(results), 'reviewed_runs': len(reviewed), 'pending_runs': pending,
              'fully_reviewed': pending == 0,
              'summary': None if pending else {
                  variant: summarize([r for r in reviewed if r['variant'] == variant])
                  for variant in sorted({r['variant'] for r in results})}}
    save_json(root / 'reviewed_summary.json', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evaluation_directory', type=Path)
    args = parser.parse_args()
    result = apply_reviews(args.evaluation_directory)
    print(f"Reviewed {result['reviewed_runs']}/{result['total_runs']}; pending {result['pending_runs']}")
    return 0 if result['fully_reviewed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
