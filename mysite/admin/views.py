from mysite.database.models import (Admin, About, AboutSection, TourCategory, Tour,
                                     TourImage,TourProgram, Region, District, Hotel, HotelImage,
                                     Transport, TransportImage, HelicopterTour, HelicopterImage,
                                    Trekking, TrekkingImage, TrekkingProgram, Contact, FAQ, TravelRequest,
                                   )
from sqladmin import ModelView




class AdminAdmin(ModelView, model= Admin):
    column_list = [Admin.username, Admin.is_active]


class AboutAdmin(ModelView, model= About):
    column_list = [About.id, About.title]


class AboutSectionAdmin(ModelView, model= AboutSection):
    column_list = [AboutSection.id, AboutSection.title]


class TourCategoryAdmin(ModelView, model= TourCategory):
    column_list = [TourCategory.id, TourCategory.name]


class TourAdmin(ModelView, model=Tour):
    column_list = [Tour.id, Tour.title]


class TourImageAdmin(ModelView, model= TourImage):
    column_list = [TourImage.id, TourImage.image]


class TourProgramAdmin(ModelView, model= TourProgram):
    column_list = [TourProgram.id, TourProgram.title]


class RegionAdmin(ModelView, model=Region):
    column_list = [Region.id, Region.image]


class DistrictAdmin(ModelView, model= District):
    column_list = [District.id, District.name]


class HotelAdmin(ModelView, model= Hotel):
    column_list = [Hotel.id, Hotel.name]


class HotelImageAdmin(ModelView, model= HotelImage):
    column_list = [HotelImage.id, HotelImage.image]


class TransportAdmin(ModelView, model= Transport):
    column_list = [Transport.id, Transport.name]


class TransportImageAdmin(ModelView, model= TransportImage):
    column_list = [TransportImage.id, TransportImage.image]


class HelicopterTourAdmin(ModelView, model= HelicopterTour):
    column_list = [HelicopterTour.id, HelicopterTour.title]


class HelicopterImageAdmin(ModelView, model= HelicopterImage):
    column_list = [HelicopterImage.id, HelicopterImage.image]


class TrekkingAdmin(ModelView, model=Trekking):
    column_list = [Trekking.id, Trekking.title]


class TrekkingImageAdmin(ModelView, model= TrekkingImage):
    column_list = [TrekkingImage.id, TrekkingImage.image]


class TrekkingProgramAdmin(ModelView, model= TrekkingProgram):
    column_list = [TrekkingProgram.id, TrekkingProgram.title]


class ContactAdmin(ModelView, model=Contact):
    column_list = [Contact.id, Contact.phone]


class FAQAdmin(ModelView, model= FAQ):
    column_list = [FAQ.id, FAQ.question, FAQ.answer, FAQ.is_active]


class TravelRequestAdmin(ModelView, model= TravelRequest):
    column_list = [TravelRequest.id, TravelRequest.name]

#
# class ChatAdmin(ModelView, model= Chat):
#     column_list = [Chat.id, Chat.client_token]
#
#
# class ChatMessageAdmin(ModelView, model= ChatMessage):
#     column_list = [ChatMessage.id, ChatMessage.text]