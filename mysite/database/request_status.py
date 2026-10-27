"""One status rule shared by API handlers and ORM writes."""


def validate_status_transition(current, proposed):
    current = getattr(current, 'value', current)
    proposed = getattr(proposed, 'value', proposed)
    if current == 'completed' and proposed != current:
        raise ValueError('Завершённую поездку нельзя вернуть в другой статус')
