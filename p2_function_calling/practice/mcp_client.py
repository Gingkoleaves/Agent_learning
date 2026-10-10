"""MCP client: lifecycle, discovery, resource/prompt reads and tool execution."""
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from practice_common.runtime import ROOT, save_json


class CourseClient:
    def __init__(self, session, initialization, trace=None):
        self.session = session
        self.initialization = initialization
        self.trace = trace
        self.schemas = []

    def record(self, method, **fields):
        if self.trace:
            self.trace.emit('mcp', method=method, **fields)

    async def discover(self):
        tools = await self.session.list_tools()
        self.schemas = [{'type': 'function', 'function': {
            'name': tool.name, 'description': tool.description or '',
            'parameters': tool.inputSchema}} for tool in tools.tools]
        self.record('tools/list', tools=[schema['function']['name'] for schema in self.schemas])
        return self.schemas

    async def call_tool(self, name, arguments):
        self.record('tools/call', name=name, arguments=arguments)
        try:
            response = await self.session.call_tool(name, arguments)
        except (McpError, OSError, TimeoutError) as error:
            raise RuntimeError('mcp_transport_error: ' + str(error)) from error
        text = '\n'.join(block.text for block in response.content if block.type == 'text')
        if response.isError:
            self.record('tool_error', name=name, message=text)
            raise ValueError(text)
        result = response.structuredContent
        if result is None:
            result = json.loads(text)
        self.record('tool_result', name=name, result=result)
        return result


@asynccontextmanager
async def connect(store_path=None, corpus_path=None, timeout=30, trace=None):
    args = ['-X', 'utf8', '-m', 'p2_function_calling.practice.mcp_server']
    if store_path:
        args += ['--store', str(store_path)]
    if corpus_path:
        args += ['--corpus', str(corpus_path)]
    parameters = StdioServerParameters(command=sys.executable, args=args, cwd=str(ROOT))
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=timeout)) as session:
            initialization = await session.initialize()
            client = CourseClient(session, initialization, trace)
            client.record('initialize', protocol=initialization.protocolVersion,
                          server=initialization.serverInfo.model_dump(mode='json'))
            await client.discover()
            yield client


async def demonstrate():
    from practice_common.runtime import Trace
    artifact_dir = ROOT / 'p2_function_calling/practice/artifacts'
    async with connect(trace=Trace(artifact_dir / 'mcp-client.jsonl')) as client:
        resources = await client.session.list_resources()
        catalog = await client.session.read_resource('course://catalog')
        prompts = await client.session.list_prompts()
        prompt = await client.session.get_prompt('compare_papers', {'topic_a': 'ReAct', 'topic_b': 'Toolformer'})
        search = await client.call_tool('search_notes', {'query': 'Toolformer'})
        evidence = search['evidence']
        paragraph = await client.call_tool('read_note', {
            'doc_id': evidence[0]['doc_id'], 'paragraph_id': evidence[0]['paragraph_id']}) if evidence else None
        output = dict(server=client.initialization.serverInfo.model_dump(mode='json'),
                      tools=client.schemas, resources=resources.model_dump(mode='json'),
                      catalog=catalog.model_dump(mode='json'), prompts=prompts.model_dump(mode='json'),
                      prompt=prompt.model_dump(mode='json'), search=search, paragraph=paragraph)
        save_json(artifact_dir / 'mcp-client.json', output)
        print(json.dumps(output, ensure_ascii=False, indent=2))


def main():
    asyncio.run(demonstrate())


if __name__ == '__main__':
    main()
