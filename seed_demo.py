"""Twenty test records per content section. Run after `alembic upgrade head`."""

from datetime import date, timedelta
from decimal import Decimal

from mysite.database.db import Base, SessionLocal
from mysite.database.models import (
    FAQ,
    About,
    AboutSection,
    Contact,
    Country,
    District,
    HelicopterImage,
    HelicopterTour,
    Hotel,
    HotelImage,
    Region,
    Tour,
    TourCategory,
    TourImage,
    TourProgram,
    TourTranslation,
    Transport,
    TransportImage,
    TravelRequest,
    Trekking,
    TrekkingImage,
    TrekkingProgram,
)
from mysite.translations.content import CONTENT_FIELDS
from mysite.translations.source import TOUR_TRANSLATION_FIELDS, source_field_hash


def seed_demo(db):
    created = 0

    def get_or_create(model, key, value, **values):
        nonlocal created
        record = db.query(model).filter(getattr(model, key) == value).first()
        if record is None:
            record = model(**{key: value}, **values)
            db.add(record)
            db.flush()
            created += 1
        return record

    def translations(field, en, de, zh):
        return {lang: {field: text} for lang, text in [('en', en), ('de', de), ('zh', zh)]}

    image = 'https://placehold.co/1200x800/png?text=TEST+'
    description = (
        'Тестовая запись для проверки сайта. Цена условная, это не предложение для бронирования.'
    )
    descriptions = {
        'en': 'Test entry for website checks. The price is a placeholder; this is not a booking offer.',
        'de': 'Testeintrag zur Website-Prüfung. Der Preis ist ein Platzhalter; dies ist kein Buchungsangebot.',
        'zh': '用于网站测试的记录。价格仅为示例，不是预订报价。',
    }

    def content(field, en, de, zh):
        result = translations(field, en, de, zh)
        for lang in result:
            result[lang]['description'] = descriptions[lang]
        return result

    country = get_or_create(
        Country,
        'name',
        'ТЕСТ: Кыргызстан',
        translations=translations(
            'name', 'TEST: Kyrgyzstan', 'TEST: Kirgisistan', '测试：吉尔吉斯斯坦'
        ),
    )
    region = get_or_create(
        Region,
        'name',
        'ТЕСТ: Чуйская область',
        country_id=country.id,
        translations=translations('name', 'TEST: Chuy', 'TEST: Tschüi', '测试：楚河州'),
    )
    district = get_or_create(
        District,
        'name',
        'ТЕСТ: Аламудунский район',
        region_id=region.id,
        translations=translations('name', 'TEST: Alamudun', 'TEST: Alamudun', '测试：阿拉穆敦'),
    )
    category = get_or_create(
        TourCategory,
        'name',
        'ТЕСТ: Экскурсии',
        image=image + 'TOUR',
        translations=translations('name', 'TEST: Excursions', 'TEST: Ausflüge', '测试：短途旅行'),
    )
    for title, english, german, chinese, latitude, longitude in [
        (
            'ТЕСТ: Ала-Арча',
            'TEST: Ala-Archa',
            'TEST: Ala-Artscha',
            '测试：阿拉阿尔恰',
            '42.6400',
            '74.4800',
        ),
        ('ТЕСТ: Бурана', 'TEST: Burana', 'TEST: Burana', '测试：布拉纳', '42.7464', '75.2508'),
    ] + [
        (
            f'ТЕСТ: Маршрут {index:02d}',
            f'TEST: Route {index:02d}',
            f'TEST: Route {index:02d}',
            f'测试：路线 {index:02d}',
            Decimal('41.5') + Decimal(index) / 100,
            Decimal('74.5') + Decimal(index) / 100,
        )
        for index in range(3, 21)
    ]:
        tour = get_or_create(
            Tour,
            'title',
            title,
            category_id=category.id,
            description=description,
            price=100,
            duration_days=1,
            latitude=latitude,
            longitude=longitude,
            main_image=image + 'TOUR',
        )
        for lang, fields in content('title', english, german, chinese).items():
            existing = db.query(TourTranslation).filter_by(tour_id=tour.id, lang=lang).first()
            if existing is None:
                source_hashes = {
                    field: source_field_hash(getattr(tour, field))
                    for field in TOUR_TRANSLATION_FIELDS
                    if getattr(tour, field) not in (None, '')
                }
                db.add(
                    TourTranslation(
                        tour_id=tour.id, lang=lang, source_hashes=source_hashes, **fields
                    )
                )
                created += 1
    get_or_create(
        Hotel,
        'name',
        'ТЕСТ: Отель в Бишкеке',
        region_id=region.id,
        district_id=district.id,
        description=description,
        price=50,
        stars=3,
        latitude='42.8746',
        longitude='74.5698',
        main_image=image + 'HOTEL',
        translations=content(
            'name', 'TEST: Bishkek hotel', 'TEST: Hotel in Bischkek', '测试：比什凯克酒店'
        ),
    )
    get_or_create(
        Transport,
        'name',
        'ТЕСТ: Минивэн',
        seats=7,
        price=80,
        description=description,
        main_image=image + 'TRANSPORT',
        translations=content('name', 'TEST: Minivan', 'TEST: Kleinbus', '测试：小型客车'),
    )
    get_or_create(
        Trekking,
        'title',
        'ТЕСТ: Поход в Ала-Арче',
        description=description,
        price=60,
        duration_days=1,
        main_image=image + 'TREKKING',
        translations=content(
            'title',
            'TEST: Ala-Archa trek',
            'TEST: Wanderung in Ala-Artscha',
            '测试：阿拉阿尔恰徒步',
        ),
    )
    flight_translations = content(
        'title', 'TEST: Helicopter flight', 'TEST: Hubschrauberflug', '测试：直升机观光'
    )
    for lang, departure, destination in [
        ('en', 'Bishkek', 'Ala-Archa'),
        ('de', 'Bischkek', 'Ala-Artscha'),
        ('zh', '比什凯克', '阿拉阿尔恰'),
    ]:
        flight_translations[lang].update(departure_location=departure, destination=destination)
    get_or_create(
        HelicopterTour,
        'title',
        'ТЕСТ: Вертолётная прогулка',
        description=description,
        price=1000,
        duration_minutes=45,
        max_passengers=4,
        departure_location='Бишкек',
        destination='Ала-Арча',
        main_image=image + 'HELICOPTER',
        translations=flight_translations,
    )
    get_or_create(
        FAQ,
        'question',
        'ТЕСТ: Можно ли забронировать эти предложения?',
        answer='Нет. Записи с пометкой ТЕСТ созданы только для проверки сайта.',
        order=0,
        translations={
            'en': {
                'question': 'TEST: Can I book these offers?',
                'answer': 'No. Entries marked TEST are only for website checks.',
            },
            'de': {
                'question': 'TEST: Kann ich diese Angebote buchen?',
                'answer': 'Nein. Einträge mit TEST dienen nur zur Website-Prüfung.',
            },
            'zh': {
                'question': '测试：可以预订这些项目吗？',
                'answer': '不可以。标有测试的记录仅用于网站测试。',
            },
        },
    )
    # Numbered variants exercise long lists, maps and language switching.
    # Coordinates and prices below are synthetic test values.
    for index in range(2, 21):
        number = f'{index:02d}'
        latitude = Decimal('42.8') + Decimal(index) / 1000
        longitude = Decimal('74.5') + Decimal(index) / 1000
        get_or_create(
            Hotel,
            'name',
            f'ТЕСТ: Отель {number}',
            region_id=region.id,
            district_id=district.id,
            description=description,
            price=40 + index * 5,
            stars=2 + index % 4,
            latitude=latitude,
            longitude=longitude,
            main_image=image + f'HOTEL+{number}',
            translations=content(
                'name', f'TEST: Hotel {number}', f'TEST: Hotel {number}', f'测试：酒店 {number}'
            ),
        )
        get_or_create(
            Transport,
            'name',
            f'ТЕСТ: Транспорт {number}',
            seats=(4, 7, 12, 18)[index % 4],
            price=50 + index * 10,
            year=2015 + index % 10,
            description=description,
            main_image=image + f'TRANSPORT+{number}',
            translations=content(
                'name',
                f'TEST: Vehicle {number}',
                f'TEST: Fahrzeug {number}',
                f'测试：车辆 {number}',
            ),
        )
        get_or_create(
            Trekking,
            'title',
            f'ТЕСТ: Поход {number}',
            description=description,
            price=30 + index * 5,
            duration_days=1 + index % 7,
            distance_km=5 + index,
            main_image=image + f'TREKKING+{number}',
            translations=content(
                'title', f'TEST: Trek {number}', f'TEST: Wanderung {number}', f'测试：徒步 {number}'
            ),
        )
        flight_translations = content(
            'title',
            f'TEST: Flight {number}',
            f'TEST: Rundflug {number}',
            f'测试：观光飞行 {number}',
        )
        for lang, departure, destination in [
            ('en', 'Bishkek (test)', f'Test destination {number}'),
            ('de', 'Bischkek (Test)', f'Testziel {number}'),
            ('zh', '比什凯克（测试）', f'测试目的地 {number}'),
        ]:
            flight_translations[lang].update(departure_location=departure, destination=destination)
        get_or_create(
            HelicopterTour,
            'title',
            f'ТЕСТ: Вертолётный маршрут {number}',
            description=description,
            price=500 + index * 100,
            duration_minutes=20 + index * 5,
            max_passengers=2 + index % 5,
            departure_location='Бишкек (тест)',
            destination=f'Тестовая точка {number}',
            main_image=image + f'HELICOPTER+{number}',
            translations=flight_translations,
        )
    for index, (ru, en, de, zh) in enumerate(
        [
            ('список туров', 'the tour list', 'die Tourliste', '旅游列表'),
            ('карточку тура', 'a tour card', 'eine Tourkarte', '旅游详情'),
            ('карту туров', 'the tour map', 'die Tourkarte', '旅游地图'),
            ('координаты', 'coordinates', 'Koordinaten', '坐标'),
            ('цены', 'prices', 'Preise', '价格'),
            ('фотографии', 'photos', 'Fotos', '照片'),
            ('длительность', 'duration', 'die Dauer', '时长'),
            ('список отелей', 'the hotel list', 'die Hotelliste', '酒店列表'),
            ('карточку отеля', 'a hotel card', 'eine Hotelkarte', '酒店详情'),
            ('транспорт', 'transport', 'Fahrzeuge', '交通工具'),
            ('количество мест', 'seating capacity', 'die Sitzplatzanzahl', '座位数'),
            ('трекинг', 'trekking', 'Wanderungen', '徒步项目'),
            ('вертолётные туры', 'helicopter tours', 'Hubschraubertouren', '直升机旅游'),
            ('число пассажиров', 'passenger capacity', 'die Passagieranzahl', '乘客人数'),
            ('место вылета', 'the departure location', 'den Abflugort', '出发地点'),
            ('пункт назначения', 'the destination', 'das Reiseziel', '目的地'),
            ('английский перевод', 'English translations', 'englische Übersetzungen', '英语翻译'),
            ('немецкий перевод', 'German translations', 'deutsche Übersetzungen', '德语翻译'),
            ('китайский перевод', 'Chinese translations', 'chinesische Übersetzungen', '中文翻译'),
        ],
        start=1,
    ):
        get_or_create(
            FAQ,
            'question',
            f'ТЕСТ: Как проверить {ru}?',
            order=index,
            answer='Откройте соответствующий раздел сайта и проверьте отображение тестовых данных. Все цены условные.',
            translations={
                'en': {
                    'question': f'TEST: How can I check {en}?',
                    'answer': 'Open the relevant website section and check the test data. All prices are placeholders.',
                },
                'de': {
                    'question': f'TEST: Wie prüfe ich {de}?',
                    'answer': 'Öffnen Sie den entsprechenden Website-Bereich und prüfen Sie die Testdaten. Alle Preise sind Platzhalter.',
                },
                'zh': {
                    'question': f'测试：如何检查{zh}？',
                    'answer': '打开网站的相应栏目并检查测试数据。所有价格仅为示例。',
                },
            },
        )

    # Complete the remaining admin content sections, including related galleries.
    # Only generated test entries are enriched; real catalogue entries are untouched.
    def photo(section, number):
        return f'https://picsum.photos/seed/kyrgyzgo-{section}-{number}/1200/800'

    def fill_missing(record, **values):
        for key, value in values.items():
            if getattr(record, key) in (None, '', []):
                setattr(record, key, value)

    def fill_translations(record, **fields):
        stored = {lang: dict(values) for lang, values in (record.translations or {}).items()}
        for key, texts in fields.items():
            for lang, text in zip(('en', 'de', 'zh'), texts):
                if not stored.setdefault(lang, {}).get(key):
                    stored[lang][key] = text
        record.translations = stored

    def named(model, label, index, **values):
        labels = {
            'Страна': ('Country', 'Land', '国家'),
            'Регион': ('Region', 'Region', '地区'),
            'Район': ('District', 'Bezirk', '区'),
            'Категория': ('Category', 'Kategorie', '类别'),
        }
        en, de, zh = labels[label]
        expected = translations(
            'name', f'TEST: {en} {index:02d}', f'TEST: {de} {index:02d}', f'测试: {zh} {index:02d}'
        )
        record = get_or_create(
            model, 'name', f'ТЕСТ: {label} {index:02d}', translations=expected, **values
        )
        old = translations(
            'name',
            f'TEST: {label} {index:02d}',
            f'TEST: {label} {index:02d}',
            f'测试: {label} {index:02d}',
        )
        stored = {lang: dict(fields) for lang, fields in (record.translations or {}).items()}
        for lang, fields in expected.items():
            if not stored.get(lang, {}).get('name') or stored[lang] == old[lang]:
                stored[lang] = fields
        record.translations = stored
        return record

    countries, regions, districts, categories = ([country], [region], [district], [category])
    for index in range(2, 21):
        countries.append(named(Country, 'Страна', index))
        regions.append(
            named(
                Region, 'Регион', index, country_id=countries[-1].id, image=photo('region', index)
            )
        )
        districts.append(named(District, 'Район', index, region_id=regions[-1].id))
        categories.append(named(TourCategory, 'Категория', index, image=photo('category', index)))
    for index, row in enumerate(regions, 1):
        if not row.image or row.image.startswith('https://placehold.co/'):
            row.image = photo('region', index)
    for index, row in enumerate(categories, 1):
        if not row.image or row.image.startswith('https://placehold.co/'):
            row.image = photo('category', index)

    for index in range(1, 21):
        number = f'{index:02d}'
        qr_code = (
            'https://api.qrserver.com/v1/create-qr-code/?size=400x400'
            f'&data=https%3A%2F%2Fexample.invalid%2Ftest-office%2F{number}'
        )
        for model, label, section in [
            (About, 'О компании', 'about'),
            (AboutSection, 'Раздел о компании', 'about-section'),
        ]:
            values = (
                {'order': index}
                if model is AboutSection
                else {
                    'experience_years': index,
                    'travelers_count': 100 * index,
                    'branches_count': index,
                    'destinations_count': 20,
                    'routes_count': 20,
                }
            )
            get_or_create(
                model,
                'title',
                f'ТЕСТ: {label} {number}',
                description=description,
                image=photo(section, number),
                translations=content(
                    'title',
                    f'TEST: About {number}',
                    f'TEST: Über uns {number}',
                    f'测试: 关于我们 {number}',
                ),
                **values,
            )
        contact = get_or_create(
            Contact,
            'email',
            f'test-office-{number}@example.com',
            country='ТЕСТ: Кыргызстан',
            city=f'ТЕСТ: Город {number}',
            phone=f'+1 202-555-01{number}',
            whatsapp=f'https://wa.me/120255501{number}',
            address=f'ТЕСТ: Демонстрационная улица, {index}',
            instagram=f'https://example.invalid/instagram/{number}',
            facebook=f'https://example.invalid/facebook/{number}',
            telegram=f'https://example.invalid/telegram/{number}',
            qr_code=qr_code,
            translations={
                lang: {
                    'country': 'TEST: Kyrgyzstan',
                    'city': f'TEST: City {number}',
                    'address': f'TEST: Demonstration street {number}',
                }
                for lang in ('en', 'de', 'zh')
            },
        )
        if not contact.qr_code or contact.qr_code == photo('contact', number):
            contact.qr_code = qr_code
        contact_text = {
            'en': {
                'country': 'TEST: Kyrgyzstan',
                'city': f'TEST: City {number}',
                'address': f'TEST: Demonstration street {number}',
            },
            'de': {
                'country': 'TEST: Kirgisistan',
                'city': f'TEST: Stadt {number}',
                'address': f'TEST: Beispielstraße {number}',
            },
            'zh': {
                'country': '测试: 吉尔吉斯斯坦',
                'city': f'测试: 城市 {number}',
                'address': f'测试: 示例街道 {number}',
            },
        }
        stored = {lang: dict(fields) for lang, fields in (contact.translations or {}).items()}
        for lang, fields in contact_text.items():
            for key, value in fields.items():
                if (
                    not stored.get(lang, {}).get(key)
                    or stored[lang][key] == contact_text['en'][key]
                ):
                    stored.setdefault(lang, {})[key] = value
        contact.translations = stored
        request_email = f'test-request-{number}@example.com'
        old_request_email = f'test-request-{number}@example.invalid'
        requests = (
            db.query(TravelRequest)
            .filter(TravelRequest.email.in_((request_email, old_request_email)))
            .all()
        )
        if not requests:
            request = TravelRequest(email=request_email)
            request.name = f'ТЕСТ: Заявка {number}'
            request.phone = f'+1 202-555-01{number}'
            request.travel_date = date(2030, 6, 1) + timedelta(days=index - 1)
            request.duration_days = 1 + index % 7
            request.travelers_count = 1 + index % 6
            request.destination = f'ТЕСТ: Маршрут {number}'
            request.message = 'ТЕСТ: Демонстрационная заявка. Не связываться и не бронировать.'
            db.add(request)
            created += 1

    for model, image_model, foreign_key, section in [
        (Tour, TourImage, 'tour_id', 'tour'),
        (Hotel, HotelImage, 'hotel_id', 'hotel'),
        (Transport, TransportImage, 'transport_id', 'transport'),
        (Trekking, TrekkingImage, 'trekking_id', 'trekking'),
        (HelicopterTour, HelicopterImage, 'helicopter_id', 'helicopter'),
    ]:
        field = model.title if hasattr(model, 'title') else model.name
        records = db.query(model).filter(field.like('ТЕСТ:%')).order_by(model.id).all()
        for index, record in enumerate(records, 1):
            number = f'{index:02d}'
            if not record.main_image or record.main_image.startswith('https://placehold.co/'):
                record.main_image = photo(section, number)
            gallery = (
                db.query(image_model)
                .filter_by(**{foreign_key: record.id, 'image': photo(section + '-gallery', number)})
                .first()
            )
            if gallery is None:
                db.add(
                    image_model(
                        **{
                            foreign_key: record.id,
                            'image': photo(section + '-gallery', number),
                            'order': 1,
                        }
                    )
                )
                created += 1
            if model is Tour:
                fill_missing(
                    record,
                    included='ТЕСТ: Транспорт и услуги гида.',
                    excluded='ТЕСТ: Перелёт и личные расходы.',
                    duration_nights=0,
                    max_people=12,
                )
                for translation in record.translations:
                    included, excluded = {
                        'en': (
                            'TEST: Transport and guide.',
                            'TEST: Flights and personal expenses.',
                        ),
                        'de': (
                            'TEST: Transport und Reiseleitung.',
                            'TEST: Flüge und persönliche Ausgaben.',
                        ),
                        'zh': ('测试: 交通和导游。', '测试: 机票和个人费用。'),
                    }[translation.lang]
                    fill_missing(translation, included=included, excluded=excluded)
            elif model is Hotel:
                fill_missing(
                    record,
                    address=f'ТЕСТ: Гостиничная улица, {index}',
                    phone=f'+1 202-555-01{number}',
                    amenities=['Wi-Fi', 'Parking', 'Breakfast'],
                )
                fill_translations(
                    record,
                    address=(
                        f'TEST: Hotel street {index}',
                        f'TEST: Hotelstraße {index}',
                        f'测试: 酒店街 {index}',
                    ),
                )
            elif model is Transport:
                fill_missing(
                    record,
                    brand='TEST',
                    model=f'Demo {number}',
                    color='ТЕСТ: Белый',
                    year=2020 + index % 5,
                )
                fill_translations(record, color=('TEST: White', 'TEST: Weiß', '测试: 白色'))
            elif model is Trekking:
                fill_missing(
                    record,
                    route=f'ТЕСТ: Старт — лагерь {number} — финиш',
                    included='ТЕСТ: Гид и трансфер.',
                    requirements='ТЕСТ: Удобная обувь и вода.',
                    difficulty='ТЕСТ: Средняя',
                    duration_hours=6,
                    max_altitude=2500 + index * 10,
                    distance_km=5 + index,
                    max_people=10,
                )
                fill_translations(
                    record,
                    route=(
                        f'TEST: Start — camp {number} — finish',
                        f'TEST: Start — Lager {number} — Ziel',
                        f'测试: 起点 — 营地 {number} — 终点',
                    ),
                    included=(
                        'TEST: Guide and transfer.',
                        'TEST: Reiseleitung und Transfer.',
                        '测试: 导游和接送。',
                    ),
                    requirements=(
                        'TEST: Comfortable shoes and water.',
                        'TEST: Bequeme Schuhe und Wasser.',
                        '测试: 舒适的鞋子和饮用水。',
                    ),
                    difficulty=('TEST: Moderate', 'TEST: Mittel', '测试: 中等'),
                )
            elif model is HelicopterTour:
                fill_missing(
                    record,
                    instruction='ТЕСТ: Следовать инструкциям пилота.',
                    included='ТЕСТ: Обзорный полёт и инструктаж.',
                )
                fill_translations(
                    record,
                    instruction=(
                        "TEST: Follow the pilot's instructions.",
                        'TEST: Den Anweisungen des Piloten folgen.',
                        '测试: 请遵守飞行员的指示。',
                    ),
                    included=(
                        'TEST: Sightseeing flight and safety briefing.',
                        'TEST: Rundflug und Sicherheitseinweisung.',
                        '测试: 观光飞行和安全说明。',
                    ),
                )
            if model in (Tour, Trekking):
                program_model = TourProgram if model is Tour else TrekkingProgram
                parent_key = 'tour_id' if model is Tour else 'trekking_id'
                program_title = f'ТЕСТ: Программа {section} {number}'
                get_or_create(
                    program_model,
                    'title',
                    program_title,
                    **{parent_key: record.id},
                    day_number=1,
                    start_time='09:00',
                    end_time='17:00',
                    description=description,
                    translations=content(
                        'title',
                        f'TEST: Itinerary {number}',
                        f'TEST: Tagesprogramm {number}',
                        f'测试: 行程 {number}',
                    ),
                )
    entities = {
        mapper.class_.__tablename__: mapper.class_
        for mapper in Base.registry.mappers
        if hasattr(mapper.class_, '__tablename__')
    }
    for table_name, fields in CONTENT_FIELDS.items():
        entity = entities.get(table_name)
        if entity is None:
            continue
        for record in db.query(entity).all():
            source = {field: getattr(record, field) for field in fields}
            if not any(
                isinstance(value, str) and value.startswith(('TEST:', 'ТЕСТ:'))
                for value in source.values()
            ):
                continue
            stored = dict(record.translations or {})
            changed = False
            for language in ('en', 'de', 'zh'):
                values = stored.get(language)
                if not isinstance(values, dict):
                    continue
                values = dict(values)
                hashes = dict(values.get('_source_hashes', {}))
                for field in fields:
                    if isinstance(values.get(field), str) and values[field]:
                        hashes.setdefault(field, source_field_hash(source[field]))
                values['_source_hashes'] = hashes
                stored[language] = values
                changed = True
            if changed:
                record.translations = stored

    demo_tours = db.query(Tour).filter(Tour.title.like('ТЕСТ:%')).all()
    for tour in demo_tours:
        for row in tour.translations:
            hashes = dict(row.source_hashes or {})
            for field in TOUR_TRANSLATION_FIELDS:
                value = getattr(row, field)
                if isinstance(value, str) and value:
                    hashes.setdefault(field, source_field_hash(getattr(tour, field)))
            row.source_hashes = hashes

    db.commit()
    return created


if __name__ == '__main__':
    with SessionLocal() as session:
        print(f'Test catalogue: created {seed_demo(session)} records. Existing entries preserved.')
