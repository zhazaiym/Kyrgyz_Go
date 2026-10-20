"""Expanded demo data for Kyrgyz_GO. Run: python seed_all.py

Uses the database configured by mysite.database.db.SessionLocal.
All prices, contacts, bookings and image paths are illustrative.
Re-running updates nothing and avoids duplicates by natural keys.
"""
import os
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, func
from mysite.database.db import SessionLocal
from mysite.database.models import (
    Admin, About, AboutSection, TourCategory, Tour, TourImage, TourProgram,
    Region, District, Hotel, HotelImage, Transport, TransportImage,
    HelicopterTour, HelicopterImage, Trekking, TrekkingImage, TrekkingProgram,
    Contact, FAQ, TravelRequest, Chat, ChatMessage,
    PriceUnitChoices, TourTypeChoices, RequestStatusChoices,
)


def money(value):
    return Decimal(str(value))


def get_or_create(db, model_cls, filters, **values):
    obj = db.execute(select(model_cls).filter_by(**filters)).scalars().first()
    if obj is None:
        obj = model_cls(**filters, **values)
        db.add(obj)
        db.flush()
    return obj


def run():
    db = SessionLocal()
    try:
        # Optional administrator: requires explicit credentials; no default password.
        username = os.getenv("SEED_ADMIN_USERNAME")
        password = os.getenv("SEED_ADMIN_PASSWORD")
        if username and password:
            from passlib.context import CryptContext
            context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            get_or_create(db, Admin, {"username": username},
                          hashed_password=context.hash(password), is_active=True)

        get_or_create(db, About, {"title": "О компании Kyrgyz_GO"},
            description="Организация путешествий по Кыргызстану: горные маршруты, озёра, культура и активный отдых. Демонстрационный текст — замените официальным описанием компании.",
            experience_years=6, travelers_count=28000, branches_count=3,
            destinations_count=20, routes_count=100, is_active=True)
        for order, (title, description) in enumerate([
            ("Местные гиды", "Знакомство с природой и культурой Кыргызстана в сопровождении местных специалистов."),
            ("Гибкие маршруты", "Индивидуальные и групповые программы с учётом пожеланий путешественников."),
            ("Поддержка в поездке", "Помощь с планированием маршрута, транспортом и размещением."),
        ], 1):
            get_or_create(db, AboutSection, {"title": title}, description=description, order=order, is_active=True)

        category_names = ["Классические туры", "Приключенческие туры", "Культурные туры", "Зимние туры", "Индивидуальные туры", "Комбинированные туры"]
        categories = {name: get_or_create(db, TourCategory, {"name": name}) for name in category_names}
        tour_data = [
            ("Иссык-Куль: отдых и достопримечательности", "Классические туры", "Путешествие к озеру Иссык-Куль с остановками у живописных мест.", 12500, 3, 2, TourTypeChoices.classic, ["Выезд из Бишкека и дорога к озеру", "Экскурсии и отдых на побережье", "Возвращение в Бишкек"]),
            ("Сон-Куль: ночёвка в юрте", "Приключенческие туры", "Высокогорное озеро, пастбища и знакомство с кочевыми традициями.", 16500, 2, 1, TourTypeChoices.adventure, ["Дорога к озеру Сон-Куль", "Прогулка у озера и обратный путь"]),
            ("Ала-Арча: горный день", "Классические туры", "Однодневная поездка в национальный парк Ала-Арча.", 3500, 1, 0, TourTypeChoices.classic, ["Прогулка по ущелью и возвращение"]),
            ("Каракол и Джети-Огуз", "Культурные туры", "Природные достопримечательности и знакомство с Караколом.", 14500, 3, 2, TourTypeChoices.cultural, ["Переезд в Каракол", "Ущелье Джети-Огуз", "Возвращение"]),
            ("Зимний отдых в Караколе", "Зимние туры", "Зимняя поездка в район Каракола; активности зависят от погоды.", 18500, 3, 2, TourTypeChoices.winter, ["Прибытие и размещение", "Зимние активности", "Возвращение"]),
            ("Индивидуальный тур по Чуйской области", "Индивидуальные туры", "Маршрут с возможностью согласовать остановки и темп путешествия.", 22000, 2, 1, TourTypeChoices.individual, ["Обзорные остановки", "Продолжение маршрута и возвращение"]),
            ("Большое путешествие по Кыргызстану", "Комбинированные туры", "Комбинация природных и культурных остановок в нескольких регионах.", 49500, 7, 6, TourTypeChoices.combined, ["Бишкек", "Ала-Арча", "Переезд к Иссык-Кулю", "Каракол", "Южный берег", "Возвращение к Чуйской долине", "Завершение программы"]),
        ]
        for title, category, description, price, days, nights, kind, program in tour_data:
            tour = get_or_create(db, Tour, {"title": title},
                category_id=categories[category].id, description=description,
                included="Транспорт по программе, сопровождение (уточняется при бронировании).",
                excluded="Личные расходы и дополнительные услуги.",
                price=money(price), price_unit=PriceUnitChoices.per_person,
                duration_days=days, duration_nights=nights, min_people=1,
                max_people=12, tour_type=kind, is_active=True)
            for day, item in enumerate(program, 1):
                get_or_create(db, TourProgram, {"tour_id": tour.id, "day_number": day},
                    title=item, description=f"День {day}: {item.lower()}. Подробности согласовываются перед поездкой.",
                    start_time="09:00", end_time="18:00")
            # Example paths; files need to be added to your static folder separately.
            get_or_create(db, TourImage, {"tour_id": tour.id, "order": 1}, image=f"/static/demo/tours/{tour.id}.jpg")

        region_names = ["Чуйская область", "Иссык-Кульская область", "Нарынская область", "Ошская область", "Джалал-Абадская область", "Таласская область", "Баткенская область"]
        regions = {name: get_or_create(db, Region, {"name": name}) for name in region_names}
        district_data = [
            ("Чуйская область", "Аламудунский район"),
            ("Чуйская область", "Ысык-Атинский район"),
            ("Иссык-Кульская область", "Иссык-Кульский район"),
            ("Иссык-Кульская область", "Ак-Суйский район"),
            ("Нарынская область", "Кочкорский район"),
            ("Ошская область", "Алайский район"),
            ("Джалал-Абадская область", "Сузакский район"),
            ("Таласская область", "Бакай-Атинский район"),
            ("Баткенская область", "Кадамжайский район"),
        ]
        districts = {(r, d): get_or_create(db, District, {"region_id": regions[r].id, "name": d}) for r, d in district_data}
        hotels = [
            ("Гостевой дом у Иссык-Куля", "Иссык-Кульская область", "Иссык-Кульский район", 4200, 3),
            ("Горный гостевой дом Каракол", "Иссык-Кульская область", "Ак-Суйский район", 5500, 3),
            ("Гостевой дом в Чуйской долине", "Чуйская область", "Аламудунский район", 3900, 3),
            ("Гостевой дом Кочкор", "Нарынская область", "Кочкорский район", 3100, 2),
            ("Гостевой дом в Алае", "Ошская область", "Алайский район", 3500, 2),
            ("Гостевой дом Джалал-Абад", "Джалал-Абадская область", "Сузакский район", 4000, 3),
            ("Гостевой дом Талас", "Таласская область", "Бакай-Атинский район", 3000, 2),
            ("Гостевой дом Баткен", "Баткенская область", "Кадамжайский район", 3200, 2),
        ]
        for name, region, district, price, stars in hotels:
            hotel = get_or_create(db, Hotel, {"name": name},
                region_id=regions[region].id, district_id=districts[(region, district)].id,
                description="Демонстрационный вариант размещения. Наличие номеров и условия уточняются.",
                address=f"{region}, {district}", price=money(price),
                price_unit=PriceUnitChoices.per_night, stars=stars,
                amenities=["Wi-Fi", "Парковка", "Завтрак по запросу"], is_active=True)
            get_or_create(db, HotelImage, {"hotel_id": hotel.id, "order": 1}, image=f"/static/demo/hotels/{hotel.id}.jpg")

        transport_data = [
            ("Минивэн для экскурсий", "Toyota", "Hiace", 12, 9000, True),
            ("Внедорожник для горных маршрутов", "Toyota", "Land Cruiser", 4, 11000, True),
            ("Микроавтобус для группы", "Mercedes-Benz", "Sprinter", 18, 14000, True),
        ]
        for name, brand, model, seats, price, driver in transport_data:
            transport = get_or_create(db, Transport, {"name": name},
                brand=brand, model=model, color="Белый", seats=seats,
                description="Демонстрационный транспорт. Доступность и комплектация уточняются.",
                price=money(price), price_unit=PriceUnitChoices.per_day,
                has_driver=driver, has_air_conditioner=True, is_active=True)
            get_or_create(db, TransportImage, {"transport_id": transport.id, "order": 1}, image=f"/static/demo/transports/{transport.id}.jpg")

        helicopters = [
            ("Панорамный полёт над горными пейзажами", "Горные районы Кыргызстана", 30, 95000),
            ("Обзорный вертолётный маршрут", "Окрестности Иссык-Куля", 45, 145000),
        ]
        for title, destination, minutes, price in helicopters:
            heli = get_or_create(db, HelicopterTour, {"title": title},
                description="Демонстрационная программа. Маршрут, безопасность и доступность подтверждает оператор.",
                destination=destination, instruction="Необходимо предварительное согласование и инструктаж.",
                included="Предполагаемый полёт по согласованному маршруту.",
                price=money(price), price_unit=PriceUnitChoices.per_trip,
                duration_minutes=minutes, max_passengers=4,
                departure_location="По согласованию", is_active=True)
            get_or_create(db, HelicopterImage, {"helicopter_id": heli.id, "order": 1}, image=f"/static/demo/helicopters/{heli.id}.jpg")

        trekking_data = [
            ("Треккинг в Ала-Арче", "Ала-Арча", 1, "Средняя", 8, 3500, ["Выход на маршрут и возвращение"]),
            ("Поход к озеру Ала-Куль", "Каракол — Ала-Куль", 3, "Сложная", 25, 18500, ["Начало маршрута", "Горный участок", "Спуск и возвращение"]),
            ("Прогулка по ущелью Джети-Огуз", "Джети-Огуз", 1, "Лёгкая", 6, 4200, ["Прогулка по ущелью"]),
        ]
        for title, route, days, difficulty, distance, price, program in trekking_data:
            trek = get_or_create(db, Trekking, {"title": title},
                description="Демонстрационный пеший маршрут; сложность зависит от погоды и подготовки.",
                route=route, included="Сопровождение по согласованной программе.",
                requirements="Подходящая обувь, одежда по погоде и вода.",
                price=money(price), price_unit=PriceUnitChoices.per_person,
                duration_days=days, difficulty=difficulty, distance_km=money(distance),
                min_people=1, max_people=10, is_active=True)
            for day, item in enumerate(program, 1):
                get_or_create(db, TrekkingProgram, {"trekking_id": trek.id, "day_number": day},
                    title=item, description=f"День {day}: {item.lower()}.", start_time="08:00", end_time="17:00")
            get_or_create(db, TrekkingImage, {"trekking_id": trek.id, "order": 1}, image=f"/static/demo/trekkings/{trek.id}.jpg")

        get_or_create(db, Contact, {"email": "demo@example.com"},
            country="Кыргызстан", city="Бишкек", phone="+996 000 000 000",
            whatsapp="+996 000 000 000", address="Демонстрационный адрес — уточните у компании",
            is_active=False)
        faq_data = [
            ("Как забронировать тур?", "Выберите программу и отправьте заявку. Менеджер уточнит доступность и детали."),
            ("Входит ли транспорт в стоимость?", "Зависит от конкретного тура. Уточните список включённых услуг в описании."),
            ("Можно ли заказать индивидуальный тур?", "Да, можно отправить запрос с датами и пожеланиями к маршруту."),
            ("Какие вещи взять в горы?", "Удобную обувь, тёплую одежду, защиту от солнца и воду."),
            ("Можно ли путешествовать с детьми?", "Это зависит от сложности маршрута и возраста детей; уточните перед бронированием."),
            ("Что делать при плохой погоде?", "Оператор уточняет безопасные варианты изменения маршрута."),
        ]
        for index, (question, answer) in enumerate(faq_data, 1):
            get_or_create(db, FAQ, {"question": question}, answer=answer, order=index, is_active=True)

        # Explicitly fictional demo booking and chat; do not confuse with real leads.
        booking = get_or_create(db, TravelRequest,
            {"name": "Тестовый клиент (демо)", "phone": "+996 000 000 001"},
            email="demo-client@example.com", travel_date=date(2027, 6, 15),
            duration_days=3, travelers_count=2, destination="Иссык-Куль",
            message="Тестовая заявка для проверки API. Не является реальным бронированием.",
            status=RequestStatusChoices.new)
        chat = get_or_create(db, Chat, {"booking_id": booking.id},
            client_token=secrets.token_urlsafe(32))
        for sender, message in [
            ("client", "Здравствуйте! Это тестовое сообщение по туру на Иссык-Куль."),
            ("admin", "Здравствуйте! Это демонстрационный ответ менеджера."),
        ]:
            get_or_create(db, ChatMessage, {"chat_id": chat.id, "sender": sender, "text": message})


        # Расширенный демонстрационный каталог: безопасное повторное выполнение.
        extra_tours = [
            ("Бишкек и национальный парк Ала-Арча", "Классические туры", "Городская экскурсия и прогулка среди горных пейзажей", 6500, ["Обзорная экскурсия по Бишкеку", "Поездка в Ала-Арчу"]),
            ("Башня Бурана и ущелье Кегеты", "Культурные туры", "Исторический памятник и живописное ущелье Чуйской области", 5900, ["Башня Бурана и музей", "Прогулка по ущелью Кегеты"]),
            ("Южный берег Иссык-Куля", "Классические туры", "Каньоны, пляжи и природные достопримечательности южного побережья", 16900, ["Переезд и каньон Сказка", "Боконбаево и побережье", "Возвращение"]),
            ("Каньон Сказка и Боконбаево", "Культурные туры", "Знакомство с природой и ремесленными традициями", 8900, ["Каньон Сказка", "Мастерские и возвращение"]),
            ("Озеро Сары-Челек", "Приключенческие туры", "Поездка к озеру среди горных лесов", 24900, ["Переезд в регион", "Прогулка у озера", "Обратная дорога"]),
            ("Арсланбоб и ореховые леса", "Приключенческие туры", "Прогулки по лесным тропам и водопадам", 17900, ["Переезд в Арсланбоб", "Водопады и лес", "Возвращение"]),
            ("Ош и гора Сулайман-Тоо", "Культурные туры", "Исторические места древнего города Ош", 12900, ["Исторический центр", "Сулайман-Тоо"]),
            ("Таш-Рабат: караван-сарай", "Культурные туры", "Исторический маршрут по высокогорному Нарыну", 18900, ["Переезд в Нарын", "Караван-сарай Таш-Рабат", "Возвращение"]),
            ("Кель-Суу: высокогорное озеро", "Приключенческие туры", "Экспедиционный маршрут с учётом погоды и пограничных правил", 34900, ["Переезд в Нарын", "Подготовка и переезд", "Озеро Кель-Суу", "Обратная дорога"]),
            ("Джыргалан: горная деревня", "Приключенческие туры", "Горные пейзажи и пешие прогулки", 18900, ["Переезд в Каракол", "Прогулка в Джыргалане", "Возвращение"]),
            ("Семёновское и Григорьевское ущелья", "Классические туры", "Однодневный маршрут по северному берегу Иссык-Куля", 7900, ["Семёновское ущелье", "Григорьевское ущелье"]),
            ("Зимние каникулы на Иссык-Куле", "Зимние туры", "Зимние виды озера и прогулки в окрестностях", 19900, ["Переезд", "Зимняя программа", "Возвращение"]),
            ("Индивидуальная поездка в Каракол", "Индивидуальные туры", "Маршрут с гибким расписанием по согласованию", 25900, ["Переезд в Каракол", "Экскурсии по выбору", "Возвращение"]),
            ("Кочкор и мастерские войлока", "Культурные туры", "Знакомство с традиционными ремёслами", 9900, ["Мастер-класс", "Прогулка по Кочкору"]),
            ("Кыргызстан за десять дней", "Комбинированные туры", "Обзорный маршрут по природным и культурным достопримечательностям", 75900, ["Бишкек", "Ала-Арча", "Чуйская долина", "Север Иссык-Куля", "Каракол", "Джети-Огуз", "Южный берег", "Кочкор", "Сон-Куль", "Возвращение"]),
            ("Талас: история и горы", "Культурные туры", "Знакомство с Таласской долиной", 14900, ["Переезд в Талас", "Экскурсии и возвращение"]),
            ("Баткен: природные маршруты", "Индивидуальные туры", "Поездка по согласованному маршруту в Баткенской области", 27900, ["Прибытие", "Экскурсионный день", "Возвращение"]),
            ("Алайская долина и виды на Памир", "Приключенческие туры", "Высокогорные виды и знакомство с Алаем", 29900, ["Переезд в Ош", "Алайская долина", "Горные пейзажи", "Возвращение"]),
        ]
        for title, cat, description, price, days_list in extra_tours:
            count_days = len(days_list)
            tour = get_or_create(db, Tour, {"title": title},
                category_id=categories[cat].id, description=description + ". Программа демонстрационная и требует подтверждения организатором.",
                included="Транспорт по маршруту и сопровождение по программе (пример комплектации).",
                excluded="Личные покупки, дополнительные услуги и питание вне программы.",
                price=money(price), price_unit=PriceUnitChoices.per_person,
                duration_days=count_days, duration_nights=max(0, count_days - 1),
                min_people=1, max_people=10,
                tour_type={"Классические туры": TourTypeChoices.classic, "Приключенческие туры": TourTypeChoices.adventure,
                           "Культурные туры": TourTypeChoices.cultural, "Зимние туры": TourTypeChoices.winter,
                           "Индивидуальные туры": TourTypeChoices.individual, "Комбинированные туры": TourTypeChoices.combined}[cat],
                is_active=True)
            for i, day_title in enumerate(days_list, 1):
                get_or_create(db, TourProgram, {"tour_id": tour.id, "day_number": i},
                    title=day_title, description=f"День {i}. {day_title}. Остановки и время зависят от условий маршрута.",
                    start_time="09:00", end_time="18:00")
            for order in (1, 2, 3):
                get_or_create(db, TourImage, {"tour_id": tour.id, "order": order},
                    image=f"/static/demo/tours/{tour.id}_{order}.jpg")

        extra_districts = [
            ("Чуйская область", "Сокулукский район"), ("Чуйская область", "Московский район"),
            ("Иссык-Кульская область", "Тонский район"), ("Иссык-Кульская область", "Джети-Огузский район"),
            ("Иссык-Кульская область", "Тюпский район"), ("Нарынская область", "Ат-Башинский район"),
            ("Нарынская область", "Нарынский район"), ("Ошская область", "Кара-Суйский район"),
            ("Джалал-Абадская область", "Аксыйский район"), ("Джалал-Абадская область", "Базар-Коргонский район"),
            ("Таласская область", "Манасский район"), ("Баткенская область", "Лейлекский район"),
        ]
        for r, d in extra_districts:
            districts[(r, d)] = get_or_create(db, District, {"region_id": regions[r].id, "name": d})
        extra_hotels = [
            ("Гостевой дом Чолпон-Ата", "Иссык-Кульская область", "Иссык-Кульский район", 4900, 3),
            ("Мини-отель Бостери", "Иссык-Кульская область", "Иссык-Кульский район", 6200, 3),
            ("Гостевой дом Тамга", "Иссык-Кульская область", "Джети-Огузский район", 4100, 2),
            ("Эко-гостевой дом Боконбаево", "Иссык-Кульская область", "Тонский район", 3800, 3),
            ("Гостевой дом Джыргалан", "Иссык-Кульская область", "Ак-Суйский район", 4500, 2),
            ("Отель Нарын Центр", "Нарынская область", "Нарынский район", 5600, 3),
            ("Гостевой дом Ат-Башы", "Нарынская область", "Ат-Башинский район", 3200, 2),
            ("Гостевой дом Сары-Челек", "Джалал-Абадская область", "Аксыйский район", 4300, 2),
            ("Гостевой дом Арсланбоб", "Джалал-Абадская область", "Базар-Коргонский район", 3900, 2),
            ("Гостевой дом Ош", "Ошская область", "Кара-Суйский район", 4500, 3),
            ("Гостевой дом Сокулук", "Чуйская область", "Сокулукский район", 3500, 2),
            ("Гостевой дом Беловодское", "Чуйская область", "Московский район", 3300, 2),
            ("Гостевой дом Манас", "Таласская область", "Манасский район", 3600, 2),
            ("Гостевой дом Лейлек", "Баткенская область", "Лейлекский район", 3700, 2),
        ]
        for name, r, d, price, stars in extra_hotels:
            hotel = get_or_create(db, Hotel, {"name": name},
                region_id=regions[r].id, district_id=districts[(r, d)].id,
                description="Демонстрационный объект размещения для проверки каталога. Реальное наличие и рейтинг не подтверждены.",
                address=f"Кыргызстан, {r}, {d}", price=money(price),
                price_unit=PriceUnitChoices.per_night, stars=stars,
                amenities=["Wi-Fi", "Парковка", "Горячая вода", "Завтрак по запросу"], is_active=True)
            for order in (1, 2, 3):
                get_or_create(db, HotelImage, {"hotel_id": hotel.id, "order": order},
                    image=f"/static/demo/hotels/{hotel.id}_{order}.jpg")

        extra_transports = [
            ("Комфортный седан", "Toyota", "Camry", 4, 6500),
            ("Семейный минивэн", "Honda", "Odyssey", 7, 8500),
            ("Внедорожник для экспедиций", "Mitsubishi", "Pajero", 4, 10500),
            ("Групповой автобус", "Hyundai", "County", 25, 17000),
            ("Туристический автобус", "Mercedes-Benz", "Tourismo", 45, 29000),
            ("Минивэн премиум", "Mercedes-Benz", "V-Class", 6, 15500),
            ("Компактный кроссовер", "Subaru", "Forester", 4, 7500),
            ("Полноприводный пикап", "Toyota", "Hilux", 4, 12500),
        ]
        for name, brand, car_model, seats, price in extra_transports:
            vehicle = get_or_create(db, Transport, {"name": name},
                brand=brand, model=car_model, color="Белый", year=2020,
                seats=seats, description="Тестовый транспорт для каталога; доступность и год выпуска не подтверждены.",
                price=money(price), price_unit=PriceUnitChoices.per_day,
                has_driver=True, has_air_conditioner=True, is_active=True)
            for order in (1, 2):
                get_or_create(db, TransportImage, {"transport_id": vehicle.id, "order": order},
                    image=f"/static/demo/transports/{vehicle.id}_{order}.jpg")

        extra_heli = [
            ("Вертолётная панорама Чуйской долины", "Чуйская долина", 25, 89000),
            ("Вертолётный обзор гор Тянь-Шаня", "Тянь-Шань", 60, 199000),
            ("Панорамный полёт над ущельями", "Горные ущелья", 40, 135000),
        ]
        for title, dest, minutes, price in extra_heli:
            flight = get_or_create(db, HelicopterTour, {"title": title},
                description="Тестовая программа, не является предложением реального авиаперевозчика.",
                destination=dest, instruction="Перед полётом требуется инструктаж и подтверждение безопасности.",
                included="Полёт по утверждённому маршруту при подходящей погоде.",
                price=money(price), price_unit=PriceUnitChoices.per_trip,
                duration_minutes=minutes, max_passengers=4, departure_location="По согласованию", is_active=True)
            for order in (1, 2):
                get_or_create(db, HelicopterImage, {"helicopter_id": flight.id, "order": order},
                    image=f"/static/demo/helicopters/{flight.id}_{order}.jpg")

        extra_trekkings = [
            ("Тропа к водопаду Ак-Сай", "Ала-Арча", 1, "Средняя", 9, 4800, ["Подъём к водопаду и возвращение"]),
            ("Треккинг в ущелье Джыргалан", "Джыргалан", 2, "Средняя", 18, 11900, ["Выход на маршрут", "Горная тропа и возвращение"]),
            ("Поход по ущелью Кегеты", "Кегеты", 1, "Лёгкая", 7, 3900, ["Прогулка и возвращение"]),
            ("Треккинг в ущелье Чон-Кемин", "Чон-Кемин", 2, "Средняя", 15, 9900, ["Вход в долину", "Пеший маршрут"]),
            ("Тропа к озеру Коль-Тор", "Кегеты", 1, "Сложная", 14, 5900, ["Подъём к озеру и спуск"]),
            ("Пеший маршрут по Арсланбобу", "Арсланбоб", 2, "Средняя", 12, 10900, ["Лесные тропы", "Водопады"]),
            ("Треккинг в Каракольском ущелье", "Каракол", 2, "Средняя", 17, 12900, ["Переход в ущелье", "Прогулка и возвращение"]),
        ]
        for title, route, days, difficulty, km, price, day_list in extra_trekkings:
            trek = get_or_create(db, Trekking, {"title": title},
                description="Демонстрационный пешеходный маршрут, не заменяет оценку погодных условий и подготовки.",
                route=route, included="Сопровождение по согласованному маршруту.",
                requirements="Треккинговая обувь, тёплая одежда, вода, личная аптечка.",
                price=money(price), price_unit=PriceUnitChoices.per_person,
                duration_days=days, difficulty=difficulty, distance_km=money(km),
                min_people=1, max_people=8, is_active=True)
            for i, title_day in enumerate(day_list, 1):
                get_or_create(db, TrekkingProgram, {"trekking_id": trek.id, "day_number": i},
                    title=title_day, description=f"День {i}: {title_day}. Маршрут может корректироваться.",
                    start_time="08:00", end_time="17:00")
            for order in (1, 2, 3):
                get_or_create(db, TrekkingImage, {"trekking_id": trek.id, "order": order},
                    image=f"/static/demo/trekkings/{trek.id}_{order}.jpg")

        extra_faq = [
            ("За сколько дней лучше бронировать тур?", "Рекомендуется оставить заявку заранее. Доступность дат подтверждает менеджер."),
            ("Можно ли изменить дату поездки?", "Возможность переноса зависит от условий выбранной программы и наличия мест."),
            ("Какие способы оплаты доступны?", "Доступные способы оплаты и условия предоплаты необходимо уточнить у организатора."),
            ("Есть ли русскоязычные гиды?", "Язык сопровождения нужно согласовать до подтверждения бронирования."),
            ("Включено ли проживание?", "Проживание включено только в те программы, где это прямо указано в условиях."),
            ("Включено ли питание?", "Состав питания зависит от тура; проверьте раздел включённых услуг."),
            ("Можно ли поехать одному?", "Некоторые программы доступны индивидуально, другие требуют минимального состава группы."),
            ("Можно ли взять с собой домашнее животное?", "Возможность зависит от правил размещения и посещаемых территорий."),
            ("Есть ли трансфер из аэропорта?", "Трансфер можно обсудить с менеджером при оформлении заявки."),
            ("Нужна ли специальная подготовка для треккинга?", "Для сложных маршрутов нужна подходящая физическая подготовка и экипировка."),
            ("Что делать при изменении погоды?", "Маршрут корректируется с приоритетом безопасности участников."),
            ("Какие документы нужны для поездки?", "Требования зависят от гражданства, маршрута и приграничных зон."),
            ("Можно ли заказать корпоративный тур?", "Да, можно отправить индивидуальную заявку с числом участников и датами."),
            ("Есть ли скидки для групп?", "Возможные групповые тарифы уточняются индивидуально."),
            ("Как связаться с менеджером?", "Используйте форму обратной связи или подтверждённые контакты на сайте."),
            ("Как отменить бронирование?", "Условия отмены и возврата зависят от подтверждённого предложения."),
            ("Работают ли туры зимой?", "Часть программ сезонная; доступность зимних маршрутов зависит от погоды."),
            ("Предоставляется ли туристическое снаряжение?", "Перечень предоставляемого снаряжения нужно уточнять для конкретного тура."),
            ("Можно ли составить собственный маршрут?", "Да, индивидуальный маршрут можно обсудить через форму заявки."),
            ("Есть ли ограничения по возрасту?", "Ограничения зависят от сложности и безопасности конкретного маршрута."),
        ]
        for i, (question, answer) in enumerate(extra_faq, 7):
            get_or_create(db, FAQ, {"question": question}, answer=answer, order=i, is_active=True)

        # Дополнительные тестовые заявки и сообщения (только вымышленные клиенты).
        for i, destination in enumerate(["Сон-Куль", "Ала-Арча", "Каракол", "Ош"], 2):
            booking = get_or_create(db, TravelRequest,
                {"name": f"Тестовый клиент {i} (демо)", "phone": f"+996 000 000 00{i}"},
                email=f"demo-client-{i}@example.com", travel_date=date(2027, 7, min(i + 10, 28)),
                duration_days=i, travelers_count=2, destination=destination,
                message="Вымышленная заявка для тестирования; не обрабатывать как реальное бронирование.",
                status=RequestStatusChoices.new)
            chat = get_or_create(db, Chat, {"booking_id": booking.id}, client_token=secrets.token_urlsafe(32))
            get_or_create(db, ChatMessage,
                {"chat_id": chat.id, "sender": "client", "text": f"Здравствуйте! Интересует тестовый тур: {destination}."})
            get_or_create(db, ChatMessage,
                {"chat_id": chat.id, "sender": "admin", "text": "Спасибо! Это демонстрационный ответ менеджера."})

        db.commit()
        print("Готово: демонстрационные данные сохранены. Содержимое всех таблиц:")
        tables = [Admin, About, AboutSection, TourCategory, Tour, TourImage,
                  TourProgram, Region, District, Hotel, HotelImage, Transport,
                  TransportImage, HelicopterTour, HelicopterImage, Trekking,
                  TrekkingImage, TrekkingProgram, Contact, FAQ, TravelRequest,
                  Chat, ChatMessage]
        for cls in tables:
            count = db.scalar(select(func.count()).select_from(cls))
            print(f"{cls.__tablename__}: {count}")
        if not (username and password):
            print("Администратор не создан. Для создания задайте SEED_ADMIN_USERNAME и SEED_ADMIN_PASSWORD.")
        print("Пути /static/demo/... — заглушки; изображения нужно добавить отдельно.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
