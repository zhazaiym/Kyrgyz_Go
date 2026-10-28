def is_demo_name(value):
    return isinstance(value, str) and value.casefold().startswith(('тест:', 'test:'))
