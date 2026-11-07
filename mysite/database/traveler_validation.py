# Технический предел существующего Integer в PostgreSQL.
# Меньший бизнес-лимит можно установить отдельно.
MAX_TRAVELERS = 2_147_483_647


def validate_travelers_count(value: int, tour=None) -> int:
    if type(value) is not int or not 1 <= value <= MAX_TRAVELERS:
        raise ValueError(
            f'Количество туристов должно быть от 1 до {MAX_TRAVELERS}'
        )

    if tour is not None:
        minimum = tour.min_people if tour.min_people is not None else 1
        maximum = tour.max_people

        if value < minimum:
            raise ValueError(f'Для этого тура нужно минимум {minimum} человек')

        if maximum is not None and value > maximum:
            raise ValueError(f'Для этого тура допускается максимум {maximum} человек')

    return value
