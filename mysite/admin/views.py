from copy import deepcopy

from sqladmin import ModelView
from sqlalchemy.orm import object_session
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from mysite.database.db import SessionLocal
from mysite.database.models import (FAQ, About, AboutSection, Admin, Contact, District,
                                    HelicopterImage, HelicopterTour, Hotel, HotelImage, Region,
                                    Tour, TourCategory, TourImage, TourProgram, Transport,
                                    TransportImage, TravelRequest, Trekking, TrekkingImage,
                                    TrekkingProgram)
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
    column_list = [Admin.username, Admin.role, Admin.is_active]
    can_create = False
    form_columns = [Admin.username, Admin.role, Admin.is_active]
    column_details_exclude_list = [Admin.hashed_password]


class AboutAdmin(LocalizedAdminMixin, ModelView, model=About):
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
    column_list = [AboutSection.id, AboutSection.title, AboutSection.order]
    form_excluded_columns = [AboutSection.order]
    column_default_sort = (AboutSection.id, False)


class TourCategoryAdmin(LocalizedAdminMixin, ModelView, model=TourCategory):
    column_list = [TourCategory.id, TourCategory.name]


class TourAdmin(SelectedItemGuard, ModelView, model=Tour):
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


class TourImageAdmin(ModelView, model=TourImage):
    column_list = [TourImage.id, TourImage.image]


class TourProgramAdmin(LocalizedAdminMixin, ModelView, model=TourProgram):
    column_list = [TourProgram.id, TourProgram.title]


class RegionAdmin(LocalizedAdminMixin, ModelView, model=Region):
    column_list = [Region.id, Region.image]


class DistrictAdmin(LocalizedAdminMixin, ModelView, model=District):
    column_list = [District.id, District.name]


class HotelAdmin(SelectedItemGuard, LocalizedAdminMixin, ModelView, model=Hotel):
    column_list = [Hotel.id, Hotel.name]


class HotelImageAdmin(ModelView, model=HotelImage):
    column_list = [HotelImage.id, HotelImage.image]


class TransportAdmin(SelectedItemGuard, LocalizedAdminMixin, ModelView, model=Transport):
    column_list = [Transport.id, Transport.name]

    form_args = {'seats': {'render_kw': {'type': 'number', 'min': 1, 'step': 1}}}


class TransportImageAdmin(ModelView, model=TransportImage):
    column_list = [TransportImage.id, TransportImage.image]


class HelicopterTourAdmin(LocalizedAdminMixin, ModelView, model=HelicopterTour):
    column_list = [HelicopterTour.id, HelicopterTour.title]
    form_args = {'search_keywords': {'description': SEARCH_KEYWORDS_HINT}}


class HelicopterImageAdmin(ModelView, model=HelicopterImage):
    column_list = [HelicopterImage.id, HelicopterImage.image]


class TrekkingAdmin(LocalizedAdminMixin, ModelView, model=Trekking):
    column_list = [Trekking.id, Trekking.title]
    form_args = {'search_keywords': {'description': SEARCH_KEYWORDS_HINT}}


class TrekkingImageAdmin(ModelView, model=TrekkingImage):
    column_list = [TrekkingImage.id, TrekkingImage.image]


class TrekkingProgramAdmin(LocalizedAdminMixin, ModelView, model=TrekkingProgram):
    column_list = [TrekkingProgram.id, TrekkingProgram.title]


class ContactAdmin(LocalizedAdminMixin, ModelView, model=Contact):
    name = 'Контакт'
    name_plural = 'Контакты'

    column_list = [Contact.id, Contact.country, Contact.city, Contact.phone, Contact.whatsapp]

    form_args = {
        'phone': {'description': ('Каалаган өлкөнүн номери: +996 700 123 456, +49 30 123456')},
        'whatsapp': {'description': ('WhatsApp шилтемеси: https://wa.me/996700123456')},
    }


class FAQAdmin(LocalizedAdminMixin, ModelView, model=FAQ):
    column_list = [FAQ.id, FAQ.question, FAQ.answer, FAQ.order, FAQ.is_active]

    form_excluded_columns = [FAQ.order]
    column_default_sort = (FAQ.id, False)


class TravelRequestAdmin(ModelView, model=TravelRequest):
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
    if view is AdminAdmin:
        allowed = {'owner'}
    elif view is TravelRequestAdmin:
        allowed = {'owner', 'manager'}
    else:
        allowed = {'owner', 'catalog_editor'}

    def can_access(self, request: Request):
        admin_id = request.session.get('admin_id')
        if not request.session.get('admin_mfa') or admin_id is None:
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
    TravelRequestAdmin,
):
    _view_roles(_admin_view)
