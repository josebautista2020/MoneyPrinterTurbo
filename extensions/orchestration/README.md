# Episode Orchestration Adapter

`JsonWorkflowCheckpointStore` provides atomic local persistence for
`EpisodeWorkflowState`.

Typical use:

```python
store = JsonWorkflowCheckpointStore("output/content_studio/workflows")
state = store.load(workflow_id) or EpisodeWorkflowState(...)
orchestrator = EpisodeOrchestrator(executors, store)
state = orchestrator.run_until_blocked(state)
```

The Core orchestrator is in `extensions/content_studio/orchestration.py`.

This adapter does not call providers and does not publish content.
