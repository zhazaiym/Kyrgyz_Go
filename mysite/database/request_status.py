"""One status rule shared by API handlers and ORM writes."""

STATUS_TRANSITIONS = {
    'draft': frozenset({'draft', 'in_progress', 'completed', 'cancelled'}),
    'new': frozenset({'new', 'in_progress', 'completed', 'cancelled'}),
    'in_progress': frozenset({'draft', 'new', 'in_progress', 'completed', 'cancelled'}),
    'cancelled': frozenset({'draft', 'new', 'in_progress', 'completed', 'cancelled'}),
    'completed': frozenset({'completed'}),
}


def validate_status_transition(current, proposed):
    current = getattr(current, 'value', current)
    proposed = getattr(proposed, 'value', proposed)
    if proposed not in STATUS_TRANSITIONS.get(current, ()):
        raise ValueError('Недопустимый переход статуса')
