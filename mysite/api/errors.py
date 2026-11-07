"""Stable error codes and one Russian message catalogue for HTTP APIs."""

ERROR_MESSAGES = {
    'invalid_request': 'Проверьте данные запроса',
    'invalid_credentials': 'Неверный логин, пароль или код',
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


def error_detail(code):
    return {'code': code, 'message': ERROR_MESSAGES[code]}


async def http_error_response(request, exc):
    from starlette.responses import JSONResponse

    detail = exc.detail
    if isinstance(detail, str):
        detail = error_detail(
            STATUS_CODES.get(
                exc.status_code, 'internal_error' if exc.status_code >= 500 else 'invalid_request'
            )
        )
    return JSONResponse({'detail': detail}, status_code=exc.status_code, headers=exc.headers)
