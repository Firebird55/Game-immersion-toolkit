"""Path-free, bounded observations for an explicitly enabled browser probe."""

BROWSER_PHASES = (
    'client-loaded', 'waiting-reader', 'reader-mounted', 'animation-frame-pending',
    'ack-requested', 'ack-http-failed', 'ack-network-failed', 'reader-timeout', 'acknowledged',
)
HTTP_PHASES = frozenset({'document', 'script', 'snapshot', 'setup', 'ack'})


def sanitize_browser_diagnostics(value):
    """Never publish a challenge, URL, page contents or arbitrary failure text."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for category, allowed in (('browser', BROWSER_PHASES), ('visibility', ('visible', 'hidden'))):
        source = value.get(category)
        if isinstance(source, dict):
            selected = {stage: source[stage] for stage in ('1', '2')
                        if isinstance(source.get(stage), str) and source[stage] in allowed}
            if selected:
                result[category] = selected
    source = value.get('http')
    if isinstance(source, dict):
        selected = {name: source[name] for name in sorted(HTTP_PHASES)
                    if source.get(name) == 'pending' or
                    type(source.get(name)) is int and 100 <= source[name] <= 599}
        if selected:
            result['http'] = selected
    return result
