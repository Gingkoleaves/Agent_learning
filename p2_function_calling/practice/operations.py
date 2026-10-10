"""Host-owned write identities. The model never supplies an operation ID."""
from copy import deepcopy
from uuid import uuid4
from practice_common.runtime import JsonStore

WRITE_TOOLS = {'create_study_task', 'update_study_task'}


class OperationJournal:
    def __init__(self, path, run_id, retries=1, trace=None):
        self.store = JsonStore(path)
        self.run_id = run_id
        self.retries = retries
        self.trace = trace

    def execute(self, name, arguments, call_id, function):
        if name not in WRITE_TOOLS:
            return function(**arguments)
        state = self.store.read()
        operations = state.setdefault('operations', {})
        key = self.run_id + ':' + call_id
        record = operations.get(key)
        if record is None:
            record = dict(operation_id=str(uuid4()), run_id=self.run_id, tool=name,
                          arguments=deepcopy(arguments), status='pending')
            operations[key] = record
            self.store.write(state)
        if record['tool'] != name or record['arguments'] != arguments:
            raise ValueError('call_id reused with different arguments in the same run')
        if record['status'] == 'succeeded':
            return deepcopy(record['result'])
        for attempt in range(self.retries + 1):
            if self.trace:
                self.trace.emit('write_operation', operation_id=record['operation_id'],
                                run_id=self.run_id, tool=name, attempt=attempt + 1)
            try:
                result = function(operation_id=record['operation_id'], **deepcopy(record['arguments']))
            except ValueError as error:
                record.update(status='rejected', error=str(error))
                self.store.write(state)
                raise
            except (RuntimeError, OSError, TimeoutError) as error:
                record.update(status='outcome_unknown', error=str(error))
                self.store.write(state)
                if attempt == self.retries:
                    raise RuntimeError('write outcome unknown; resume saved operation instead of creating a new one') from error
                continue
            record.update(status='succeeded', result=deepcopy(result))
            record.pop('error', None)
            self.store.write(state)
            return result

    def resume(self, operation_id, registry):
        for key, record in self.store.read().get('operations', {}).items():
            if record['operation_id'] == operation_id:
                original_run, call_id = key.split(':', 1)
                journal = OperationJournal(self.store.path, original_run, self.retries, self.trace)
                return journal.execute(record['tool'], record['arguments'], call_id, registry[record['tool']])
        raise ValueError('unknown operation_id')


def model_schemas(schemas):
    result = deepcopy(schemas)
    for schema in result:
        parameters = schema['function']['parameters']
        parameters.get('properties', {}).pop('operation_id', None)
        if 'required' in parameters:
            parameters['required'] = [key for key in parameters['required'] if key != 'operation_id']
    return result
