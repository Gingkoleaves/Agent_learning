"""Real OTel task/model/tool spans, with opt-in LangSmith sample export."""
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor


class JsonlExporter(SpanExporter):
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans):
        with self.path.open('a', encoding='utf-8') as stream:
            for span in spans:
                stream.write(json.dumps(json.loads(span.to_json()), ensure_ascii=False) + '\n')
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


class Observability:
    def __init__(self, root, langsmith=False):
        self.path = Path(root) / 'spans.jsonl'
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(self.path)))
        self.tracer = self.provider.get_tracer('agent-learn.p6')
        self.parent = ContextVar('p6_langsmith_parent', default=None)
        self.remote = None
        self.langsmith = {'status': 'disabled'}
        self.sample_taken = False
        if langsmith:
            self.langsmith = {'status': 'not_configured'}
            if os.environ.get('LANGSMITH_API_KEY'):
                from langsmith import Client
                self.remote = Client(timeout_ms=5000, auto_batch_tracing=False)
                self.langsmith = {'status': 'configured_upload_not_verified'}

    @contextmanager
    def span(self, name, **attributes):
        """Mirror one task and its children; remote errors never fail scoring."""
        run, token = None, None
        with self.tracer.start_as_current_span(name, attributes=attributes) as span:
            parent = self.parent.get()
            if self.remote and (parent is not None or (name == 'task' and not self.sample_taken)):
                try:
                    kind = 'llm' if name.startswith('model.') else ('tool' if name.startswith('tool.') else 'chain')
                    if parent:
                        run = parent.create_child(name=name, run_type=kind, inputs=attributes)
                    else:
                        from langsmith import RunTree
                        self.sample_taken = True
                        run = RunTree(name='p6.task', run_type='chain', inputs=attributes,
                            client=self.remote, project_name=os.environ.get('LANGSMITH_PROJECT', 'agent-learn-p6'))
                    run.post()
                    token = self.parent.set(run)
                except Exception as error:
                    self.langsmith = {'status': 'upload_failed', 'error_type': type(error).__name__}
                    run = None
            failure = None
            try:
                yield span
            except BaseException as error:
                failure = type(error).__name__
                raise
            finally:
                if token is not None:
                    self.parent.reset(token)
                if run is not None:
                    try:
                        run.end(outputs={'otel_trace_id': format(span.get_span_context().trace_id, '032x')}, error=failure)
                        run.patch()
                        run.wait()
                        if parent is None and self.langsmith['status'] != 'upload_failed':
                            self.remote.read_run(run.id)
                            self.langsmith = {'status': 'verified', 'run_id': str(run.id), 'url': run.get_url()}
                    except Exception as error:
                        self.langsmith = {'status': 'upload_failed', 'error_type': type(error).__name__}

    def close(self):
        self.provider.shutdown()
        if self.remote:
            self.remote.close()

    def annotate(self, *, inputs=None, outputs=None):
        run = self.parent.get()
        if run is not None:
            try:
                if inputs is not None:
                    run.add_inputs(inputs)
                if outputs is not None:
                    run.add_outputs(outputs)
            except Exception as error:
                self.langsmith = {'status': 'upload_failed', 'error_type': type(error).__name__}


class Recorder:
    def __init__(self, path, obs, max_tools=24):
        self.path, self.obs, self.events = Path(path), obs, []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tool_calls, self.max_tools = 0, max_tools

    def emit(self, event, **fields):
        row = dict(event=event, **fields)
        self.events.append(row)
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')

    def tool(self, name, function, *, call_id=None, **arguments):
        if self.tool_calls >= self.max_tools:
            raise RuntimeError('tool_call_budget_exhausted')
        self.tool_calls += 1
        call_id = call_id or f'tool-{self.tool_calls}'
        with self.obs.span('tool.' + name, call_id=call_id):
            self.obs.annotate(inputs={'arguments': arguments})
            self.emit('tool_start', name=name, call_id=call_id, arguments=arguments)
            try:
                result = function(**arguments)
            except Exception as error:
                self.emit('tool_error', name=name, call_id=call_id, error=str(error))
                raise
            self.emit('tool_end', name=name, call_id=call_id, result=result)
            self.obs.annotate(outputs={'result': result})
            return result


class ObservedModel:
    def __init__(self, model, recorder, max_calls=8):
        self.model, self.recorder, self.max_calls = model, recorder, max_calls
        self.model_name = getattr(model, 'model_name', 'scripted')
        self.calls, self.usage = 0, {}

    async def arespond(self, messages, tools=None):
        if self.calls >= self.max_calls:
            raise RuntimeError('model_call_budget_exhausted')
        self.calls += 1
        with self.recorder.obs.span('model.call', call_id=f'model-{self.calls}', model=self.model_name) as span:
            self.recorder.obs.annotate(inputs={'messages': messages, 'tools': tools})
            self.recorder.emit('model_input', messages=messages, tools=tools)
            response = await self.model.arespond(messages, tools)
            for key, value in (response.get('usage') or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self.usage[key] = self.usage.get(key, 0) + value
                    span.set_attribute('usage.' + key, value)
            self.recorder.emit('model_output', response=response)
            self.recorder.obs.annotate(outputs=response)
            return response
