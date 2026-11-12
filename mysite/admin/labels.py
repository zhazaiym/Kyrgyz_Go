from datetime import UTC, timedelta, timezone

from sqlalchemy import DateTime, inspect

FIELD_LABELS = {
    'address': 'Адрес',
    'admin_id': 'Администратор',
    'amenities': 'Удобства',
    'answer': 'Ответ',
    'app_id': 'ID приложения',
    'branches_count': 'Филиалов',
    'brand': 'Марка',
    'category': 'Категория',
    'category_id': 'Категория',
    'city': 'Город',
    'client_id': 'Клиент',
    'color': 'Цвет',
    'country': 'Страна',
    'country_id': 'Страна',
    'created_at': 'Создано',
    'day_number': 'День',
    'departure_location': 'Место вылета',
    'description': 'Описание',
    'destination': 'Направление',
    'destinations_count': 'Направлений',
    'difficulty': 'Сложность',
    'distance_km': 'Расстояние, км',
    'district': 'Район',
    'district_id': 'Район',
    'districts': 'Районы',
    'duration_days': 'Длительность, дней',
    'duration_hours': 'Длительность, часов',
    'duration_minutes': 'Длительность, мин',
    'duration_nights': 'Ночей',
    'email': 'Email',
    'end_time': 'Конец',
    'excluded': 'Не входит в цену',
    'experience_years': 'Лет опыта',
    'expires_at': 'Действует до',
    'facebook': 'Facebook',
    'has_air_conditioner': 'Кондиционер',
    'has_driver': 'С водителем',
    'hashed_password': 'Хэш пароля',
    'helicopter': 'Вертолётный тур',
    'helicopter_id': 'Вертолётный тур',
    'hotel': 'Отель',
    'hotel_id': 'Отель',
    'hotels': 'Отели',
    'id': 'ID',
    'image': 'Фото',
    'images': 'Фото',
    'included': 'Входит в цену',
    'instagram': 'Instagram',
    'instruction': 'Инструктаж',
    'is_active': 'Показывать на сайте',
    'last_used_at': 'Последнее использование',
    'latitude': 'Широта',
    'longitude': 'Долгота',
    'main_image': 'Главное фото',
    'max_altitude': 'Макс. высота, м',
    'max_passengers': 'Макс. пассажиров',
    'max_people': 'Макс. человек',
    'message': 'Сообщение',
    'min_people': 'Мин. человек',
    'model': 'Модель',
    'name': 'Название',
    'order': 'Порядок',
    'phone': 'Телефон',
    'poster_url': 'Обложка видео',
    'previous_refresh_hash': 'Предыдущий токен',
    'price': 'Цена',
    'price_unit': 'Цена за',
    'programs': 'Программа',
    'qr_code': 'QR-код',
    'question': 'Вопрос',
    'refresh_hash': 'Токен',
    'region': 'Регион',
    'region_id': 'Регион',
    'requirements': 'Требования',
    'revoked_at': 'Отозвано',
    'role': 'Роль',
    'rotated_at': 'Обновлено',
    'route': 'Маршрут',
    'routes_count': 'Маршрутов',
    'search_keywords': 'Слова для поиска',
    'seats': 'Мест',
    'selected_services': 'Выбранные услуги',
    'selection_id': 'Подборка',
    'source': 'Источник',
    'stars': 'Звёзд',
    'start_time': 'Начало',
    'status': 'Статус',
    'telegram': 'Telegram',
    'title': 'Название',
    'tour': 'Тур',
    'tour_id': 'Тур',
    'tour_type': 'Тип тура',
    'tours': 'Туры',
    'translations': 'Переводы',
    'transport': 'Транспорт',
    'transport_id': 'Транспорт',
    'travel_date': 'Дата поездки',
    'travelers_count': 'Путешественников',
    'updated_at': 'Изменено',
    'user_agent': 'Браузер',
    'username': 'Логин',
    'video_url': 'Видео',
    'videos': 'Видео',
    'whatsapp': 'WhatsApp',
    'year': 'Год',
}
MODEL_LABELS = {'TravelRequest': {'name': 'Имя клиента'}}


def apply_labels(view):
    fields = {attribute.key for attribute in inspect(view.model).attrs}
    labels = {key: label for key, label in FIELD_LABELS.items() if key in fields}
    labels.update(MODEL_LABELS.get(view.model.__name__, {}))
    labels.update(view.column_labels)
    view.column_labels = labels


CHOICE_LABELS = {
    'price_unit': {
        'per_person': 'за человека',
        'per_day': 'за день',
        'per_night': 'за ночь',
        'per_hour': 'за час',
        'per_trip': 'за поездку',
    },
    'tour_type': {
        'classic': 'Классический',
        'adventure': 'Приключения',
        'cultural': 'Культурный',
        'winter': 'Зимний',
        'individual': 'Индивидуальный',
        'combined': 'Комбинированный',
    },
    'status': {
        'new': 'Новая',
        'in_progress': 'В работе',
        'completed': 'Завершена',
        'cancelled': 'Отменена',
    },
    'role': {
        'owner': 'Владелец',
        'manager': 'Менеджер заявок',
        'catalog_editor': 'Редактор каталога',
    },
}
AUTOMATIC_FIELDS = ('created_at', 'updated_at')
BISHKEK = timezone(timedelta(hours=6))


def choice_text(name):
    labels = CHOICE_LABELS[name]

    def formatter(model, attribute):
        value = getattr(model, name)
        value = getattr(value, 'value', value)
        return labels.get(value, value)

    return formatter


def local_time(name):
    def formatter(model, attribute):
        value = getattr(model, name)
        if value is None:
            return ''
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(BISHKEK).strftime('%d.%m.%Y %H:%M')

    return formatter


def apply_form_rules(view):
    mapper = inspect(view.model)
    if not view.form_columns:
        hidden = [relation.key for relation in mapper.relationships if relation.uselist]
        hidden += [name for name in AUTOMATIC_FIELDS if name in mapper.attrs]
        view.form_excluded_columns = [*view.form_excluded_columns, *hidden]
    formatters = {name: choice_text(name) for name in CHOICE_LABELS if name in mapper.attrs}
    for attribute in mapper.column_attrs:
        if isinstance(attribute.columns[0].type, DateTime):
            formatters[attribute.key] = local_time(attribute.key)
    view.column_formatters = {**formatters, **view.column_formatters}
    view.column_formatters_detail = {**formatters, **view.column_formatters_detail}
    original = view.scaffold_form

    async def scaffold_form(self, rules=None):
        form = await original(self, rules)
        for name, labels in CHOICE_LABELS.items():
            field = getattr(form, name, None)
            choices = getattr(field, 'kwargs', {}).get('choices')
            if choices:
                field.kwargs['choices'] = [
                    (value, labels.get(value, value)) for value, _ in choices
                ]
        return form

    view.scaffold_form = scaffold_form
