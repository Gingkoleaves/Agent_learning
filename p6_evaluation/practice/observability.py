"""Actual OTel spans on disk, and optional LangSmith callbacks for P5."""
import json
import os
from contextlib import contextmanager
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode


class JsonlExporter(SpanExporter):
    def __init__(self, path):
        self.path = path

    def export(self, spans):
        with self.path.open('a', encoding='utf-8') as stream:
            for span in spans:
                # to_json includes trace_id, span_id, parent_id, times and events.
                stream.write(json.dumps(json.loads(span.to_json()), ensure_ascii=False) + '\n')
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


class Observability:
    def __init__(self, root):
        self.path = Path(root) / 'spans.jsonl'
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(self.path)))
        self.tracer = self.provider.get_tracer('agent-learn.p6')
        self.callbacks = []
        self.langsmith = 'not_configured'
        if os.environ.get('LANGSMITH_API_KEY'):
            from langchain_core.tracers.langchain import LangChainTracer
            self.callbacks = [LangChainTracer(project_name=os.environ.get('LANGSMITH_PROJECT', 'agent-learn-p6'))]
            self.langsmith = 'configured_upload_not_verified'

    @contextmanager
    def span(self, name, **attributes):
        with self.tracer.start_as_current_span(name, attributes=attributes) as span:
            yield span

    def close(self):
        self.provider.shutdown()
        if self.callbacks:
            from langchain_core.tracers.langchain import wait_for_all_tracers
            wait_for_all_tracers()


class Recorder:
    def __init__(self, path, obs):
        self.path, self.obs, self.events = path, obs, []
        self.tool_calls = 0

    def emit(self, event, **fields):
        row = dict(event=event, **fields)
        self.events.append(row)
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')

    def tool(self, name, function, **arguments):
        self.tool_calls += 1
        call_id = f'tool-{self.tool_calls}'
        with self.obs.span('tool.' + name, call_id=call_id) as span:
            self.emit('tool_start', name=name, call_id=call_id, arguments=arguments)
            try:
                result = function(**arguments)
            except Exception as error:
                self.emit('tool_error', name=name, call_id=call_id, error=str(error))
                raise
            self.emit('tool_end', name=name, call_id=call_id, result=result)
            span.set_attribute('result', json.dumps(result, ensure_ascii=False))
            return result


class ObservedModel:
    def __init__(self, model, recorder):
        self.model, self.recorder = model, recorder
        self.calls, self.usage = 0, {}

    async def arespond(self, messages, tools=None):
        self.calls += 1
        with self.recorder.obs.span('model.call', call_id=f'model-{self.calls}',
                                    model=getattr(self.model, 'model_name', 'scripted')) as span:
            self.recorder.emit('model_input', messages=messages, tools=tools)
            response = await self.model.arespond(messages, tools)
            for key, value in (response.get('usage') or {}).items():
                if isinstance(value, (int, float)):
                    self.usage[key] = self.usage.get(key, 0) + value
                    span.set_attribute('usage.' + key, value)
            self.recorder.emit('model_output', response=response)
            return response
