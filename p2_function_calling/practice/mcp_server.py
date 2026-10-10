"""Official MCP SDK server. stdout is reserved for the stdio protocol."""
import argparse
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from p1_basic_concepts.practice.solution import read_note as local_read, search_notes as local_search
from p2_function_calling.practice.solution import validate_arguments, create_study_task as local_create, get_study_task as local_get, update_study_task as local_update
from practice_common.runtime import ROOT, JsonStore, load_jsonl


def build_server(corpus, store):
    server = FastMCP('agent-learn-p2')

    @server.tool()
    def search_notes(query: str) -> dict:
        """Search local notes by keyword and return evidence with document/paragraph IDs."""
        validate_arguments('search_notes', {'query': query}, corpus)
        return {'evidence': local_search(query, corpus)}

    @server.tool()
    def read_note(doc_id: str, paragraph_id: str) -> dict:
        """Read one exact paragraph identified by document and paragraph IDs."""
        return {'evidence': [local_read(doc_id, paragraph_id, corpus)]}

    @server.tool()
    def create_study_task(title: str, due_date: str, source_ids: list[str], operation_id: str) -> dict:
        """Save a task. source_ids are document IDs (e.g. p2-note), not paragraph IDs. Host supplies operation_id."""
        arguments = dict(title=title, due_date=due_date, source_ids=source_ids)
        validate_arguments('create_study_task', arguments, corpus)
        return local_create(store=store, operation_id=operation_id, **arguments)

    @server.tool()
    def update_study_task(task_id: str, operation_id: str, title: str | None = None,
                          due_date: str | None = None, source_ids: list[str] | None = None,
                          status: str | None = None) -> dict:
        """Update an existing task by ID. Provide fields to change, not a new create request."""
        arguments = dict(task_id=task_id, title=title, due_date=due_date, source_ids=source_ids, status=status)
        validate_arguments('update_study_task', arguments, corpus)
        return local_update(store=store, operation_id=operation_id, **arguments)

    @server.tool()
    def get_study_task(task_id: str) -> dict:
        """Read the persisted task to verify that a write actually succeeded."""
        return local_get(task_id, store)

    @server.resource('course://catalog', mime_type='application/json')
    def course_catalog() -> str:
        """List available document IDs and source files."""
        documents = {note['doc_id']: note['source'] for note in corpus}
        return json.dumps(documents, ensure_ascii=False)

    @server.prompt()
    def compare_papers(topic_a: str, topic_b: str) -> str:
        """Compare two topics using evidence from the local course notes."""
        return f'比较 {topic_a} 与 {topic_b}，说明机制、优点和局限；先查资料，再引用文档与段落，不编造来源。'

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, default=ROOT / 'data/corpus.jsonl')
    parser.add_argument('--store', type=Path, default=ROOT / 'p2_function_calling/practice/artifacts/study_tasks.json')
    args = parser.parse_args()
    build_server(load_jsonl(args.corpus), JsonStore(args.store)).run(transport='stdio')


if __name__ == '__main__':
    main()
