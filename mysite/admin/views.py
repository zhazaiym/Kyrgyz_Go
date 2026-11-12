from copy import deepcopy

from markupsafe import Markup
from sqladmin import ModelView
from sqlalchemy.orm import object_session
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from wtforms import PasswordField, validators

from mysite.admin.labels import apply_labels
from mysite.api.provider_secrets import open_secret, seal_secret
from mysite.api.social_auth import WITHOUT_SECRET, valid_app_id, valid_secret
from mysite.database.db import SessionLocal
from mysite.database.models import (FAQ, About, AboutSection, Admin, Contact, District,
                                    HelicopterImage, HelicopterTour, Hotel, HotelImage, Region,
                                    Tour, TourCategory, TourImage, TourProgram, TourVideo,
                                    Transport, TransportImage, TravelRequest, Trekking,
                                    TrekkingImage, TrekkingProgram)
from mysite.database.social_models import AuthProvider
from mysite.translations.content import (CONTENT_FIELDS, generate_translations,
                                         manual_translation_changed,
                                         manual_translation_needs_refresh, mark_manual_translations,
                                         release_stale_manual_translations)
from mysite.translations.jobs import enqueue_translation
from mysite.translations.source import (TOUR_TRANSLATION_FIELDS, normalize_text, source_field_hash,
                                        source_value_changed)
from mysite.translations.translator import translate_tour

SEARCH_KEYWORDS_HINT = (
    'Слова для поиска в чате через запятую: местные названия и варианты написания, '
    'например «Ысык-Көл, Issyk-Kul»'
)


class SelectedItemGuard:
    async def delete_model(self, request, pk):
        from sqlalchemy.exc import IntegrityError

        from mysite.api.errors import ERROR_MESSAGES

        try:
            await super().delete_model(request, pk)
        except IntegrityError:
            raise ValueError(ERROR_MESSAGES['selected_item_in_use']) from None

    async def on_model_delete(self, model, request):
        from mysite.api.deletion_guards import protect_selected_item

        def check():
            with SessionLocal() as db:
                from fastapi import HTTPException

                try:
                    protect_selected_item(db, type(model), model.id)
                except HTTPException as exc:
                    raise ValueError(exc.detail['message']) from None

        await run_in_threadpool(check)


class RequestSourceFilter:
    title = 'Источник'
    parameter_name = 'source'
    has_operator = False
    template = 'sqladmin/filters/lookup_filter.html'

    async def lookups(self, request, model, run_query):
        return [('__all', 'Все'), ('chat', 'Чат'), ('site', 'Сайт')]

    async def get_filtered_query(self, query, value, model):
        return query.where(TravelRequest.source == value) if value in {'chat', 'site'} else query


class LocalizedAdminMixin:
    async def on_model_change(self, data, model, is_created, request):
        fields = CONTENT_FIELDS[model.__tablename__]
        form_translation_snapshot = deepcopy(model.translations)
        session = object_session(model)
        if not is_created and session is not None:
            # Serialize this form save with translation workers and merge against
            # the submitted snapshot instead of overwriting a worker's newer JSON.
            await run_in_threadpool(session.refresh, model, with_for_update=True)
        for field in fields:
            if field in data:
                data[field] = normalize_text(data[field])
        source_changed = is_created or any(
            field in data and source_value_changed(getattr(model, field, None), data[field])
            for field in fields
        )
        source = {field: data.get(field, getattr(model, field, None)) for field in fields}
        refresh_cleared_fields = False
        if 'translations' in data:
            submitted_translations = data['translations']
            refresh_cleared_fields = manual_translation_needs_refresh(
                submitted_translations, form_translation_snapshot, model.translations
            )
            if manual_translation_changed(submitted_translations, form_translation_snapshot):
                data['translations'] = mark_manual_translations(
                    submitted_translations,
                    source,
                    model.translations,
                    compared_to=form_translation_snapshot,
                )
            else:
                data['translations'] = model.translations or {}
        if source_changed or ('translations' in data and refresh_cleared_fields):
            data['translations'] = release_stale_manual_translations(
                data.get('translations', model.translations), source
            )
            request.state.catalogue_source = source

    async def after_model_change(self, data, model, is_created, request):
        source = getattr(request.state, 'catalogue_source', None)
        if source is not None:
            enqueue_translation(type(model), model.id, source, generate_translations)


class AdminAdmin(ModelView, model=Admin):
    name = 'Администратор'
    name_plural = 'Администраторы'
    icon = 'fa-solid fa-user-shield'
    category = 'Доступ'
    category_icon = 'fa-solid fa-lock'
    column_list = [Admin.username, Admin.role, Admin.is_active]
    can_create = False
    form_columns = [Admin.username, Admin.role, Admin.is_active]
    column_details_exclude_list = [Admin.hashed_password]


class AboutAdmin(LocalizedAdminMixin, ModelView, model=About):
    name = 'О компании'
    name_plural = 'О компании'
    icon = 'fa-solid fa-building'
    category = 'Сайт'
    category_icon = 'fa-solid fa-globe'
    column_list = [About.id, About.title]

    form_excluded_columns = [
        About.experience_years,
        About.travelers_count,
        About.branches_count,
        About.destinations_count,
        About.routes_count,
    ]

    column_details_exclude_list = form_excluded_columns


class AboutSectionAdmin(LocalizedAdminMixin, ModelView, model=AboutSection):
    name = 'Раздел «О нас»'
    name_plural = 'Разделы «О нас»'
    icon = 'fa-solid fa-layer-group'
    category = 'Сайт'
    category_icon = 'fa-solid fa-globe'
    column_list = [AboutSection.id, AboutSection.title, AboutSection.order]
    form_excluded_columns = [AboutSection.order]
    column_default_sort = (AboutSection.id, False)


class TourCategoryAdmin(LocalizedAdminMixin, ModelView, model=TourCategory):
    name = 'Категория тура'
    name_plural = 'Категории туров'
    icon = 'fa-solid fa-tags'
    category = 'Туры'
    category_icon = 'fa-solid fa-route'
    column_list = [TourCategory.id, TourCategory.name]


class TourAdmin(SelectedItemGuard, ModelView, model=Tour):
    name = 'Тур'
    name_plural = 'Туры'
    icon = 'fa-solid fa-map-location-dot'
    category = 'Туры'
    category_icon = 'fa-solid fa-route'
    column_list = [Tour.id, Tour.title]
    form_args = {'search_keywords': {'description': SEARCH_KEYWORDS_HINT}}

    # Админге «Ночей» талаасын көрсөтпөйбүз
    form_excluded_columns = [Tour.duration_nights]

    async def on_model_change(self, data, model, is_created, request):
        for field in TOUR_TRANSLATION_FIELDS:
            if field in data:
                data[field] = normalize_text(data[field])
        days = data.get('duration_days')

        if days is not None:
            if days < 1:
                raise ValueError('Күндүн саны 1ден аз болбошу керек')

            # Мисалы: 5 күн = 4 түн
            data['duration_nights'] = days - 1
        else:
            data['duration_nights'] = None

        changed_fields = set()
        for field in TOUR_TRANSLATION_FIELDS:
            if isinstance(data.get(field), str):
                data[field] = normalize_text(data[field])
            if field in data and source_value_changed(getattr(model, field, None), data[field]):
                changed_fields.add(field)
        request.state.tour_source_changed = is_created or bool(changed_fields)
        if changed_fields:
            source = {
                field: data.get(field, getattr(model, field, None))
                for field in TOUR_TRANSLATION_FIELDS
            }
            for translation in model.translations:
                hashes = translation.source_hashes or {}
                translation.manual_fields = [
                    field
                    for field in (translation.manual_fields or [])
                    if field not in changed_fields
                    and hashes.get(field) == source_field_hash(source.get(field))
                ]

    async def after_model_change(self, data, model, is_created, request):
        if request.state.tour_source_changed:
            await run_in_threadpool(self._refresh_translations, model.id)

    @staticmethod
    def _refresh_translations(tour_id):
        with SessionLocal() as db:
            tour = db.get(Tour, tour_id)
            if tour is None:
                return
            source = {field: getattr(tour, field) for field in TOUR_TRANSLATION_FIELDS}
        enqueue_translation(Tour, tour_id, source, translate_tour)


class TourVideoAdmin(ModelView, model=TourVideo):
    name = 'Видео тура'
    name_plural = 'Видео туров'
    icon = 'fa-solid fa-film'
    category = 'Туры'
    category_icon = 'fa-solid fa-route'
    column_list = [
        TourVideo.id,
        TourVideo.tour_id,
        TourVideo.video_url,
        TourVideo.poster_url,
        TourVideo.order,
    ]
    form_columns = [TourVideo.tour, TourVideo.video_url, TourVideo.poster_url, TourVideo.order]
    column_default_sort = [(TourVideo.order, False), (TourVideo.id, False)]


class TourImageAdmin(ModelView, model=TourImage):
    name = 'Фото тура'
    name_plural = 'Фото туров'
    icon = 'fa-solid fa-images'
    category = 'Туры'
    category_icon = 'fa-solid fa-route'
    column_list = [TourImage.id, TourImage.image]


class TourProgramAdmin(LocalizedAdminMixin, ModelView, model=TourProgram):
    name = 'Программа тура'
    name_plural = 'Программы туров'
    icon = 'fa-solid fa-list-check'
    category = 'Туры'
    category_icon = 'fa-solid fa-route'
    column_list = [TourProgram.id, TourProgram.title]


class RegionAdmin(LocalizedAdminMixin, ModelView, model=Region):
    name = 'Регион'
    name_plural = 'Регионы'
    icon = 'fa-solid fa-earth-asia'
    category = 'География'
    category_icon = 'fa-solid fa-map'
    column_list = [Region.id, Region.image]


class DistrictAdmin(LocalizedAdminMixin, ModelView, model=District):
    name = 'Район'
    name_plural = 'Районы'
    icon = 'fa-solid fa-location-dot'
    category = 'География'
    category_icon = 'fa-solid fa-map'
    column_list = [District.id, District.name]


class HotelAdmin(SelectedItemGuard, LocalizedAdminMixin, ModelView, model=Hotel):
    name = 'Отель'
    name_plural = 'Отели'
    icon = 'fa-solid fa-hotel'
    category = 'Отели'
    category_icon = 'fa-solid fa-bed'
    column_list = [Hotel.id, Hotel.name]


class HotelImageAdmin(ModelView, model=HotelImage):
    name = 'Фото отеля'
    name_plural = 'Фото отелей'
    icon = 'fa-solid fa-images'
    category = 'Отели'
    category_icon = 'fa-solid fa-bed'
    column_list = [HotelImage.id, HotelImage.image]


class TransportAdmin(SelectedItemGuard, LocalizedAdminMixin, ModelView, model=Transport):
    name = 'Транспорт'
    name_plural = 'Транспорт'
    icon = 'fa-solid fa-car-side'
    category = 'Транспорт'
    category_icon = 'fa-solid fa-car'
    column_list = [Transport.id, Transport.name]

    form_args = {'seats': {'render_kw': {'type': 'number', 'min': 1, 'step': 1}}}


class TransportImageAdmin(ModelView, model=TransportImage):
    name = 'Фото транспорта'
    name_plural = 'Фото транспорта'
    icon = 'fa-solid fa-images'
    category = 'Транспорт'
    category_icon = 'fa-solid fa-car'
    column_list = [TransportImage.id, TransportImage.image]


class HelicopterTourAdmin(LocalizedAdminMixin, ModelView, model=HelicopterTour):
    name = 'Вертолётный тур'
    name_plural = 'Вертолётные туры'
    icon = 'fa-solid fa-helicopter'
    category = 'Вертолёты'
    category_icon = 'fa-solid fa-helicopter'
    column_list = [HelicopterTour.id, HelicopterTour.title]
    form_args = {'search_keywords': {'description': SEARCH_KEYWORDS_HINT}}


class HelicopterImageAdmin(ModelView, model=HelicopterImage):
    name = 'Фото вертолётного тура'
    name_plural = 'Фото вертолётных туров'
    icon = 'fa-solid fa-images'
    category = 'Вертолёты'
    category_icon = 'fa-solid fa-helicopter'
    column_list = [HelicopterImage.id, HelicopterImage.image]


class TrekkingAdmin(LocalizedAdminMixin, ModelView, model=Trekking):
    name = 'Треккинг'
    name_plural = 'Треккинги'
    icon = 'fa-solid fa-person-hiking'
    category = 'Треккинг'
    category_icon = 'fa-solid fa-mountain'
    column_list = [Trekking.id, Trekking.title]
    form_args = {'search_keywords': {'description': SEARCH_KEYWORDS_HINT}}


class TrekkingImageAdmin(ModelView, model=TrekkingImage):
    name = 'Фото треккинга'
    name_plural = 'Фото треккингов'
    icon = 'fa-solid fa-images'
    category = 'Треккинг'
    category_icon = 'fa-solid fa-mountain'
    column_list = [TrekkingImage.id, TrekkingImage.image]


class TrekkingProgramAdmin(LocalizedAdminMixin, ModelView, model=TrekkingProgram):
    name = 'Программа треккинга'
    name_plural = 'Программы треккингов'
    icon = 'fa-solid fa-list-check'
    category = 'Треккинг'
    category_icon = 'fa-solid fa-mountain'
    column_list = [TrekkingProgram.id, TrekkingProgram.title]


class ContactAdmin(LocalizedAdminMixin, ModelView, model=Contact):
    icon = 'fa-solid fa-address-book'
    category = 'Сайт'
    category_icon = 'fa-solid fa-globe'
    name = 'Контакт'
    name_plural = 'Контакты'

    column_list = [Contact.id, Contact.country, Contact.city, Contact.phone, Contact.whatsapp]

    form_args = {
        'phone': {'description': ('Каалаган өлкөнүн номери: +996 700 123 456, +49 30 123456')},
        'whatsapp': {'description': ('WhatsApp шилтемеси: https://wa.me/996700123456')},
    }


class FAQAdmin(LocalizedAdminMixin, ModelView, model=FAQ):
    name = 'Вопрос и ответ'
    name_plural = 'Вопросы и ответы'
    icon = 'fa-solid fa-circle-question'
    category = 'Сайт'
    category_icon = 'fa-solid fa-globe'
    column_list = [FAQ.id, FAQ.question, FAQ.answer, FAQ.order, FAQ.is_active]

    form_excluded_columns = [FAQ.order]
    column_default_sort = (FAQ.id, False)


APP_ID_HINTS = {
    'google': 'Client ID вида 1234567890-abc123.apps.googleusercontent.com. Секрет не нужен.',
    'facebook': 'App ID из цифр. Секрет не нужен.',
    'vk': 'ID приложения VK ID (цифры) и защищённый ключ. VK ID пускает и аккаунты Mail.ru и Одноклассников.',
    'telegram': 'Имя бота без @ (оканчивается на bot) и токен бота от @BotFather.',
    'yandex': 'ClientID (32 символа) и Client secret с oauth.yandex.ru.',
    'x': 'OAuth 2.0 Client ID и Client Secret с developer.x.com.',
    'github': 'Client ID и Client secret OAuth-приложения GitHub.',
    'discord': 'Client ID (цифры) и Client Secret из раздела OAuth2.',
    'microsoft': 'Application (client) ID и секрет приложения в Microsoft Entra.',
    'tiktok': 'Client key и Client secret из TikTok for Developers.',
    'apple': (
        'Services ID (например com.kerben.travel.web). Секрет: Team ID, пробел, Key ID, '
        'пробел и содержимое файла .p8 целиком.'
    ),
    'kakao': 'REST API ключ и Client Secret (раздел «Безопасность», включить).',
    'naver': 'Client ID и Client Secret из Naver Developers.',
    'line': 'Channel ID (цифры) и Channel secret канала LINE Login.',
}
SECRET_HINT = (
    'Хранится в базе зашифрованным и здесь больше не показывается. '
    'Оставьте пустым, чтобы не менять. Для Google и Facebook не нужен.'
)


def provider_title(model, attribute):
    hint = APP_ID_HINTS.get(model.provider, '')
    return Markup(
        '<strong>{}</strong><div class="kt-provider-hint text-secondary small">{}</div>'
    ).format(model.title, hint)


def provider_callback(model, attribute):
    if model.provider in WITHOUT_SECRET:
        return 'не нужен'
    if model.provider == 'telegram':
        return 'домен сайта в @BotFather (/setdomain)'
    return f'/auth/oauth/{model.provider}/callback'


def provider_secret(model, attribute):
    if model.provider in WITHOUT_SECRET:
        return 'не нужен'
    return 'сохранён' if open_secret(model.client_secret) else 'нет'


class AuthProviderAdmin(ModelView, model=AuthProvider):
    name = 'Вход через соцсеть'
    name_plural = 'Вход через соцсети'
    icon = 'fa-solid fa-right-to-bracket'
    category = 'Сайт'
    category_icon = 'fa-solid fa-globe'
    can_create = False
    can_delete = False
    column_list = [
        AuthProvider.title,
        AuthProvider.is_active,
        AuthProvider.app_id,
        AuthProvider.client_secret,
        AuthProvider.provider,
        AuthProvider.updated_at,
    ]
    column_details_list = column_list
    column_labels = {AuthProvider.client_secret: 'Секрет', AuthProvider.provider: 'Адрес возврата'}
    column_formatters = {
        AuthProvider.title: provider_title,
        AuthProvider.client_secret: provider_secret,
        AuthProvider.provider: provider_callback,
    }
    column_formatters_detail = column_formatters
    column_default_sort = (AuthProvider.title, False)
    page_size = 50
    form_columns = [AuthProvider.app_id, AuthProvider.is_active]

    async def scaffold_form(self, rules=None):
        form = await super().scaffold_form(rules)
        form.secret = PasswordField(
            'Секретный ключ',
            validators=[validators.Optional()],
            description=SECRET_HINT,
            render_kw={'class': 'form-control', 'autocomplete': 'new-password'},
        )
        return form

    async def on_model_change(self, data, model, is_created, request):
        hint = APP_ID_HINTS.get(model.provider, '')
        app_id = (data.get('app_id') or '').strip() or None
        secret = (data.pop('secret', None) or '').strip() or None
        data['app_id'] = app_id
        if app_id is not None and not valid_app_id(model.provider, app_id):
            raise ValueError(f'Это не похоже на ID приложения {model.title}. {hint}')
        if secret is not None:
            if model.provider in WITHOUT_SECRET:
                raise ValueError(f'Для {model.title} секрет не нужен, не вставляйте его сюда.')
            if not valid_secret(model.provider, secret):
                raise ValueError(f'Это не похоже на секретный ключ {model.title}. {hint}')
            data['client_secret'] = seal_secret(secret)
        if not data.get('is_active'):
            return
        if app_id is None:
            raise ValueError('Чтобы включить вход, сначала вставьте ID приложения')
        stored = data.get('client_secret', model.client_secret)
        if model.provider not in WITHOUT_SECRET and not valid_secret(
            model.provider, open_secret(stored)
        ):
            raise ValueError(f'Чтобы включить вход через {model.title}, вставьте секретный ключ')


class TravelRequestAdmin(ModelView, model=TravelRequest):
    icon = 'fa-solid fa-paper-plane'
    name = 'Заявка'
    name_plural = 'Все заявки'
    column_list = [
        TravelRequest.id,
        TravelRequest.source,
        TravelRequest.name,
        TravelRequest.phone,
        TravelRequest.destination,
        TravelRequest.travel_date,
        TravelRequest.travelers_count,
        TravelRequest.status,
        TravelRequest.created_at,
    ]
    column_searchable_list = [TravelRequest.name, TravelRequest.phone, TravelRequest.destination]
    column_sortable_list = [
        TravelRequest.id,
        TravelRequest.source,
        TravelRequest.travel_date,
        TravelRequest.status,
        TravelRequest.created_at,
    ]
    column_default_sort = [(TravelRequest.created_at, True), (TravelRequest.id, True)]
    column_filters = [RequestSourceFilter()]
    column_labels = {TravelRequest.source: 'Источник'}
    can_view_details = True

    can_create = False
    can_delete = False
    form_columns = [TravelRequest.status]


def _view_roles(view):
    if view in (AdminAdmin, AuthProviderAdmin):
        allowed = {'owner'}
    elif view is TravelRequestAdmin:
        allowed = {'owner', 'manager'}
    else:
        allowed = {'owner', 'catalog_editor'}

    def can_access(self, request: Request):
        admin_id = request.session.get('admin_id')
        if admin_id is None:
            return False
        with SessionLocal() as db:
            admin = db.get(Admin, admin_id)
            return bool(admin and admin.is_active and admin.role in allowed)

    view.is_accessible = can_access
    view.is_visible = can_access


for _admin_view in (
    AdminAdmin,
    AboutAdmin,
    AboutSectionAdmin,
    TourCategoryAdmin,
    TourImageAdmin,
    TourVideoAdmin,
    TourAdmin,
    TourProgramAdmin,
    RegionAdmin,
    DistrictAdmin,
    HotelAdmin,
    HotelImageAdmin,
    TransportAdmin,
    TransportImageAdmin,
    HelicopterTourAdmin,
    HelicopterImageAdmin,
    TrekkingAdmin,
    TrekkingImageAdmin,
    TrekkingProgramAdmin,
    ContactAdmin,
    FAQAdmin,
    AuthProviderAdmin,
    TravelRequestAdmin,
):
    _view_roles(_admin_view)
    apply_labels(_admin_view)
