from backend.native_browser_probe import sanitize_browser_diagnostics


def test_browser_diagnostics_are_small_and_never_forward_arbitrary_data():
    assert sanitize_browser_diagnostics(None) == {}
    assert sanitize_browser_diagnostics({'browser': ['private-value']}) == {}
    value = {'browser': {'1': 'animation-frame-pending', '2': 'private-value', '3': 'client-loaded'},
             'visibility': {'1': 'hidden', '2': []}, 'http': {'document': 200, 'snapshot': 'pending',
             'script': 503, 'setup': True, 'ack': 'private-value', '/private-url': 200},
             'token': 'private-challenge'}
    assert sanitize_browser_diagnostics(value) == {
        'browser': {'1': 'animation-frame-pending'}, 'visibility': {'1': 'hidden'},
        'http': {'document': 200, 'script': 503, 'snapshot': 'pending'}}
