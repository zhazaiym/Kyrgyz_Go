from sqladmin import ModelView
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from mysite.database.chat_models import ChatBookingLink
from mysite.database.models import (FAQ, About, AboutSection, Admin, Contact, District,
                                    HelicopterImage, HelicopterTour, Hotel, HotelImage, Region,
                                    Tour, TourCategory, TourImage, TourProgram, Transport,
                                    TransportImage, TravelRequest, Trekking, TrekkingImage,
                                    TrekkingProgram)
from mysite.translations.content import CONTENT_FIELDS, generate_translations


class LocalizedAdminMixin:
    async def on_model_change(self, data, model, is_created, request):
        fields = CONTENT_FIELDS[model.__tablename__]
        source_changed = is_created or any(
            field in data and data[field] != getattr(model, field, None) for field in fields
        )
        manual_translation = bool(data.get('translations')) and (
            is_created or data['translations'] != model.translations
        )
        if source_changed and not manual_translation:
            source = {field: data.get(field, getattr(model, field, None)) for field in fields}
            data['translations'] = await run_in_threadpool(generate_translations, source)


class AdminAdmin(ModelView, model=Admin):
    column_list = [Admin.username, Admin.is_active]
    can_create = False
    form_columns = [Admin.username, Admin.is_active]
    column_details_exclude_list = [Admin.hashed_password]


# class AboutAdmin(LocalizedAdminMixin, ModelView, model= About):
#     column_list = [About.id, About.title]
#
#
# class AboutSectionAdmin(LocalizedAdminMixin, ModelView, model= AboutSection):
#     column_list = [AboutSection.id, AboutSection.title]


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


# class TourAdmin(ModelView, model=Tour):
#     column_list = [Tour.id, Tour.title]
#
#     async def on_model_change(self, data, model, is_created, request):
#         from mysite.api.tour import TRANSLATED_FIELDS
#
#         request.state.tour_source_changed = is_created or any(
#             field in data and data[field] != getattr(model, field, None)
#             for field in TRANSLATED_FIELDS
#         )
#
#     async def after_model_change(self, data, model, is_created, request):
#         if request.state.tour_source_changed:
#             await run_in_threadpool(self._refresh_translations, model.id)
#
#     @staticmethod
#     def _refresh_translations(tour_id):
#         from mysite.api.tour import try_save_translations
#         from mysite.database.db import SessionLocal
#         from mysite.database.models import TourTranslation
#
#         with SessionLocal() as db:
#             tour = db.get(Tour, tour_id)
#             if tour is None:
#                 return
#             db.query(TourTranslation).filter_by(tour_id=tour_id).delete(synchronize_session=False)
#             db.flush()
#             try_save_translations(tour, db)
#             db.commit()


class TourAdmin(ModelView, model=Tour):
    column_list = [Tour.id, Tour.title]

    # Админге «Ночей» талаасын көрсөтпөйбүз
    form_excluded_columns = [Tour.duration_nights]

    async def on_model_change(self, data, model, is_created, request):
        from mysite.api.tour import TRANSLATED_FIELDS

        days = data.get('duration_days')

        if days is not None:
            if days < 1:
                raise ValueError('Күндүн саны 1ден аз болбошу керек')

            # Мисалы: 5 күн = 4 түн
            data['duration_nights'] = days - 1
        else:
            data['duration_nights'] = None

        request.state.tour_source_changed = is_created or any(
            field in data and data[field] != getattr(model, field, None)
            for field in TRANSLATED_FIELDS
        )

    async def after_model_change(self, data, model, is_created, request):
        if request.state.tour_source_changed:
            await run_in_threadpool(self._refresh_translations, model.id)

    @staticmethod
    def _refresh_translations(tour_id):
        from mysite.api.tour import try_save_translations
        from mysite.database.db import SessionLocal
        from mysite.database.models import TourTranslation

        with SessionLocal() as db:
            tour = db.get(Tour, tour_id)
            if tour is None:
                return
            db.query(TourTranslation).filter_by(tour_id=tour_id).delete(synchronize_session=False)
            db.flush()
            try_save_translations(tour, db)
            db.commit()


class TourImageAdmin(ModelView, model=TourImage):
    column_list = [TourImage.id, TourImage.image]


class TourProgramAdmin(LocalizedAdminMixin, ModelView, model=TourProgram):
    column_list = [TourProgram.id, TourProgram.title]


class RegionAdmin(LocalizedAdminMixin, ModelView, model=Region):
    column_list = [Region.id, Region.image]


class DistrictAdmin(LocalizedAdminMixin, ModelView, model=District):
    column_list = [District.id, District.name]


class HotelAdmin(LocalizedAdminMixin, ModelView, model=Hotel):
    column_list = [Hotel.id, Hotel.name]


class HotelImageAdmin(ModelView, model=HotelImage):
    column_list = [HotelImage.id, HotelImage.image]


# class TransportAdmin(LocalizedAdminMixin, ModelView, model= Transport):
#     column_list = [Transport.id, Transport.name]


class TransportAdmin(LocalizedAdminMixin, ModelView, model=Transport):
    column_list = [Transport.id, Transport.name]

    form_args = {'seats': {'render_kw': {'type': 'number', 'min': 1, 'step': 1}}}


class TransportImageAdmin(ModelView, model=TransportImage):
    column_list = [TransportImage.id, TransportImage.image]


class HelicopterTourAdmin(LocalizedAdminMixin, ModelView, model=HelicopterTour):
    column_list = [HelicopterTour.id, HelicopterTour.title]


class HelicopterImageAdmin(ModelView, model=HelicopterImage):
    column_list = [HelicopterImage.id, HelicopterImage.image]


class TrekkingAdmin(LocalizedAdminMixin, ModelView, model=Trekking):
    column_list = [Trekking.id, Trekking.title]


class TrekkingImageAdmin(ModelView, model=TrekkingImage):
    column_list = [TrekkingImage.id, TrekkingImage.image]


class TrekkingProgramAdmin(LocalizedAdminMixin, ModelView, model=TrekkingProgram):
    column_list = [TrekkingProgram.id, TrekkingProgram.title]


# class ContactAdmin(LocalizedAdminMixin, ModelView, model=Contact):
#     column_list = [Contact.id, Contact.phone]
#
#
# class FAQAdmin(LocalizedAdminMixin, ModelView, model= FAQ):
#     column_list = [FAQ.id, FAQ.question, FAQ.answer, FAQ.is_active]


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
        TravelRequest.travel_date,
        TravelRequest.status,
        TravelRequest.created_at,
    ]
    column_default_sort = (TravelRequest.created_at, True)
    can_view_details = True


class ChatRequestAdmin(TravelRequestAdmin):
    identity = 'chat-request'
    name = 'Заявка из чата'
    name_plural = 'Заявки из чата'
    can_create = False
    can_delete = False
    form_columns = [TravelRequest.status]

    def list_query(self, request):
        return (
            super()
            .list_query(request)
            .where(TravelRequest.id.in_(select(ChatBookingLink.request_id)))
        )

    def count_query(self, request):
        return (
            super()
            .count_query(request)
            .where(TravelRequest.id.in_(select(ChatBookingLink.request_id)))
        )

    def form_details_query(self, request):
        return (
            super()
            .form_details_query(request)
            .where(TravelRequest.id.in_(select(ChatBookingLink.request_id)))
        )

    def form_edit_query(self, request):
        return (
            super()
            .form_edit_query(request)
            .where(TravelRequest.id.in_(select(ChatBookingLink.request_id)))
        )
