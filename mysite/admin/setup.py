from .views import (AdminAdmin, AboutAdmin, AboutSectionAdmin,
                    TourCategoryAdmin, TourAdmin, TourImageAdmin,
                    TourProgramAdmin, RegionAdmin, DistrictAdmin,
                    HotelAdmin, HotelImageAdmin, TransportAdmin,
                    TransportImageAdmin, HelicopterTourAdmin, HelicopterImageAdmin,
                    TrekkingAdmin, TrekkingImageAdmin, TrekkingProgramAdmin,
                    ContactAdmin, FAQAdmin, TravelRequestAdmin,
                    ChatAdmin, ChatMessageAdmin)

from fastapi import FastAPI
from sqladmin import Admin
from mysite.database.db import engine

def setup_admin(auth_app: FastAPI):
    admin = Admin(auth_app, engine)
    admin.add_view(AdminAdmin)
    admin.add_view(AboutAdmin)
    admin.add_view(AboutSectionAdmin)
    admin.add_view(TourCategoryAdmin)
    admin.add_view(TourImageAdmin)
    admin.add_view(TourAdmin)
    admin.add_view(TourProgramAdmin)
    admin.add_view(RegionAdmin)
    admin.add_view(DistrictAdmin)
    admin.add_view(HotelAdmin)
    admin.add_view(HotelImageAdmin)
    admin.add_view(TransportAdmin)
    admin.add_view(TransportImageAdmin)
    admin.add_view(HelicopterTourAdmin)
    admin.add_view(HelicopterImageAdmin)
    admin.add_view(TrekkingAdmin)
    admin.add_view(TrekkingImageAdmin)
    admin.add_view(TrekkingProgramAdmin)
    admin.add_view(ContactAdmin)
    admin.add_view(FAQAdmin)
    admin.add_view(TravelRequestAdmin)
    admin.add_view(ChatAdmin)
    admin.add_view(ChatMessageAdmin)

