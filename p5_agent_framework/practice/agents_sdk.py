"""OpenAI Agents SDK practice: model-driven retrieval and a validated study plan."""
import asyncio
import json
import time

from agents import Agent, Model, ModelResponse, Runner, RunConfig, function_tool
from agents.exceptions import MaxTurnsExceeded
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from .solution import PROMPT, Nodes, emit, parse_plan, validate_plan, result_of
from .state import initial_state


class CourseModel(Model):
    """Translate SDK Responses items to the course's asynchronous model interface."""
    def __init__(self, context):
        self.context = context
        self.calls = 0
        self.usage = {}
        self.peak = 0

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        config = self.context.get('config', {})
        if self.calls >= config.get('max_model_calls', 8):
            raise RuntimeError('budget_exhausted')
        messages = [{'role': 'system', 'content': system_instructions}]
        items = [{'role': 'user', 'content': input}] if isinstance(input, str) else input
        for item in items:
            item = item if isinstance(item, dict) else item.model_dump()
            if item.get('type') == 'function_call':
                call = dict(type='tool_call', call_id=item['call_id'], name=item['name'],
                            arguments=json.loads(item['arguments']))
                if messages[-1]['role'] == 'assistant' and isinstance(messages[-1]['content'], dict):
                    messages[-1]['content']['calls'].append(call)
                else:
                    messages.append(dict(role='assistant', content=dict(type='tool_calls', calls=[call])))
            elif item.get('type') == 'function_call_output':
                messages.append(dict(role='tool', tool_call_id=item['call_id'], content=item['output']))
            elif 'role' in item:
                content = item.get('content', '')
                if isinstance(content, list):
                    content = ''.join(part.get('text', '') for part in content)
                messages.append(dict(role=item['role'], content=content))
        schemas = [dict(type='function', function=dict(name=t.name, description=t.description,
                   parameters=t.params_json_schema)) for t in tools]
        self.peak = max(self.peak, len(json.dumps([messages, schemas], ensure_ascii=False)))
        if self.peak + config.get('reserve_output_tokens', 500) > config.get('context_token_budget', 6000):
            raise RuntimeError('context_exhausted')
        self.calls += 1
        response = await self.context['model'].arespond(messages, schemas)
        emit(self.context, 'sdk_model_response', response=response)
        usage = response.get('usage') or {}
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                self.usage[key] = self.usage.get(key, 0) + value
        if response.get('type') in ('tool_call', 'tool_calls'):
            output = [ResponseFunctionToolCall(type='function_call', call_id=c['call_id'],
                name=c['name'], arguments=json.dumps(c['arguments'], ensure_ascii=False))
                for c in response.get('calls', [response])]
        else:
            output = [ResponseOutputMessage(id=f'message-{self.calls}', type='message',
                role='assistant', status='completed', content=[ResponseOutputText(type='output_text',
                text=response.get('answer', ''), annotations=[])])]
        return ModelResponse(output=output, response_id=None, usage=Usage(requests=1,
            input_tokens=usage.get('prompt_tokens', 0), output_tokens=usage.get('completion_tokens', 0),
            total_tokens=usage.get('total_tokens', 0)))

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError('This practice uses Runner.run, not streaming')
        yield


async def execute(payload, context):
    if payload.get('resume') or payload.get('decision') is not None:
        raise ValueError('SDK practice generates a plan; use LangGraph for confirmation and recovery')
    started = time.monotonic()
    state = initial_state(payload)
    nodes = Nodes(context)
    state.update(await nodes.load_profile(state))
    model = CourseModel(context)
    retrieved = False

    @function_tool
    async def search_notes(query: str) -> str:
        """Search local course notes once and return paragraphs with source IDs."""
        nonlocal retrieved
        if not retrieved:
            state['query'] = query
            state.update(await nodes.retrieve(state))
            retrieved = True
        return json.dumps({'evidence': state['evidence']}, ensure_ascii=False)

    agent = Agent(name='study-planner', model=model, tools=[search_notes],
        instructions=PROMPT.replace('检索已经完成。', '先调用 search_notes 获取实际证据，再生成计划。'))
    user = json.dumps({k: state[k] for k in ('question', 'query', 'profile', 'start_date')}, ensure_ascii=False)
    config = context.get('config', {})
    try:
        result = await asyncio.wait_for(Runner.run(agent, user,
            max_turns=config.get('max_rounds', 8), run_config=RunConfig(tracing_disabled=True)),
            config.get('timeout_seconds', 30))
        state['candidate_plan'] = parse_plan({'answer': result.final_output})
        state['validation_errors'] = validate_plan(state['candidate_plan'], state)
        state['status'] = ('no_evidence' if not state['evidence'] else
                           'validation_failed' if state['validation_errors'] else 'planned')
        emit(context, 'sdk_run_items', items=[item.to_input_item() for item in result.new_items])
    except MaxTurnsExceeded:
        state['status'] = 'budget_exhausted'
    except TimeoutError:
        state['status'] = 'timeout'
    except (RuntimeError, ValueError) as error:
        reason = str(error)
        state['status'] = reason if reason in ('budget_exhausted', 'context_exhausted') else 'model_error'
        state['validation_errors'] = [reason]
    state['metrics'].update(model_calls=model.calls, usage=model.usage,
        usage_kind='provider' if model.usage else 'unavailable', peak_input_tokens_estimate=model.peak)
    return result_of(state, started, 'agents_sdk')
