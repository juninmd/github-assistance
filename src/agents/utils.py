The conflict is resolved. The merged version keeps:
- `log_func: Callable[..., None] | None = None` (from upstream/master, preserving the specific type hint)
- `cached_sessions: list[dict] | None = None` (from HEAD, since the function body references this parameter)