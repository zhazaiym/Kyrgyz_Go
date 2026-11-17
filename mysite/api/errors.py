"""Stable error codes and one Russian message catalogue for HTTP APIs."""

ERROR_MESSAGES = {
    'invalid_request': 'Проверьте данные запроса',
    'invalid_credentials': 'Неверный логин или пароль',
    'authentication_required': 'Войдите в аккаунт для доступа',
    'forbidden': 'Недостаточно прав',
    'not_found': 'Запись не найдена',
    'conflict': 'Действие недоступно в текущем состоянии',
    'validation_error': 'Проверьте введённые данные',
    'rate_limited': 'Слишком много попыток, попробуйте позже',
    'service_unavailable': 'Сервис временно недоступен',
    'selected_item_in_use': 'Используется в подборке, снимите с публикации',
    'invalid_travel_date': 'Дата поездки не может быть в прошлом',
    'invalid_travelers_count': 'Проверьте допустимое число туристов',
    'unsuitable_hotel': 'Этот отель не подходит к выбранному туру, выберите из предложенных',
    'unsuitable_transport': 'Этот транспорт не подходит к выбранному туру, выберите из предложенных',
    'file_too_large': 'Файл слишком большой',
    'review_requires_trip': 'Отзыв можно оставить после завершённой поездки по этому туру',
    'internal_error': 'Не удалось выполнить запрос',
}
STATUS_CODES = {
    400: 'invalid_request',
    401: 'authentication_required',
    403: 'forbidden',
    404: 'not_found',
    409: 'conflict',
    422: 'validation_error',
    429: 'rate_limited',
    502: 'service_unavailable',
    503: 'service_unavailable',
    504: 'service_unavailable',
}


SUCCESS_MESSAGES = {
    'deleted': 'Запись удалена',
    'translated': 'Перевод выполнен',
    'directions_ready': 'Направления созданы',
}


def success_detail(code):
    """A finished action: a stable code for the site and a Russian text for people."""
    return {'code': code, 'message': SUCCESS_MESSAGES[code]}


def error_detail(code):
    return {'code': code, 'message': ERROR_MESSAGES[code]}


async def database_busy_response(_request, _exc):
    """Every pooled database connection is taken: ask the client to retry instead of a 500."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        {'detail': error_detail('service_unavailable')},
        status_code=503,
        headers={'Retry-After': '2'},
    )


async def http_error_response(_request, exc):
    from starlette.responses import JSONResponse

    detail = exc.detail
    if isinstance(detail, str):
        detail = error_detail(
            STATUS_CODES.get(
                exc.status_code, 'internal_error' if exc.status_code >= 500 else 'invalid_request'
            )
        )
    return JSONResponse({'detail': detail}, status_code=exc.status_code, headers=exc.headers)
