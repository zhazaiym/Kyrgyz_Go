"""Source-checked walking itineraries, without company prices or service promises.

Geographical names use Russian / operator-published Latin forms. German and
Chinese keep the Latin proper names rather than inventing translated toponyms.
"""

LANGUAGES = ('ru', 'en', 'de', 'zh')
CHECKED_ON = '2026-11-09'
DK = 'https://destinationkarakol.com/tours/hiking-trekking/'
JY = 'https://jyrgalan.com/what-to-do/trekking/'
PARK = 'https://alaarchapark.com/trails'


def names(ru, latin):
    return dict(zip(LANGUAGES, (ru, latin, latin, latin)))


def text(ru, en, de, zh):
    return dict(zip(LANGUAGES, (ru, en, de, zh)))


REGIONS = {
    'karakol': names(
        'Кыргызстан, Иссык-Кульская область, Терскей Ала-Тоо',
        'Kyrgyzstan, Issyk-Kul Region, Terskey Ala-Too',
    ),
    'jyrgalan': names(
        'Кыргызстан, Иссык-Кульская область, окрестности Жыргалана',
        'Kyrgyzstan, Issyk-Kul Region, Jyrgalan',
    ),
    'kochkor': names(
        'Кыргызстан, Нарынская область, Кочкорский район',
        'Kyrgyzstan, Naryn Region, Kochkor District',
    ),
    'songkol': names(
        'Кыргызстан, Нарынская область, Кызарт — Сон-Куль',
        'Kyrgyzstan, Naryn Region, Kyzart — Song-Kol',
    ),
    'chuy': names(
        'Кыргызстан, Чуйская область, Кыргызский хребет', 'Kyrgyzstan, Chuy Region, Kyrgyz Ala-Too'
    ),
    'boom': names('Кыргызстан, Боомское ущелье, Конорчек', 'Kyrgyzstan, Boom Gorge, Konorchek'),
}
SEASONS = {
    'jun-sep': text('июнь–сентябрь', 'June–September', 'Juni–September', '6月至9月'),
    'may-oct': text('май–октябрь', 'May–October', 'Mai–Oktober', '5月至10月'),
    'jun-aug': text('июнь–август', 'June–August', 'Juni–August', '6月至8月'),
    'jun-oct': text('июнь–октябрь', 'June–October', 'Juni–Oktober', '6月至10月'),
    'spring-autumn': text(
        'весна и ранняя осень; только в сухую погоду',
        'spring and early autumn; dry weather only',
        'Frühling und Frühherbst; nur bei trockenem Wetter',
        '春季和初秋；仅限干燥天气',
    ),
    'late-spring': text(
        'конец весны — начало лета',
        'late spring–early summer',
        'Spätfrühling–Frühsommer',
        '晚春至初夏',
    ),
}
DIFFICULTY = {
    'easy': text('Лёгкая', 'Easy', 'Leicht', '简单'),
    'medium': text('Средняя', 'Moderate', 'Mittel', '中等'),
    'hard': text('Сложная', 'Hard', 'Schwer', '困难'),
    'conflicting': text(
        'Классификация источника противоречива; требуется уточнение',
        'Conflicting source grading; confirmation required',
        'Widersprüchliche Einstufung; Klärung erforderlich',
        '来源难度分级不一致，需确认',
    ),
}
REQUIREMENTS = text(
    'Обувь для горных троп, защита от дождя и холода, вода и питание. '
    'Перед выходом проверить погоду, доступность тропы и собственную подготовку. '
    'Ночёвки, сопровождение, транспорт и питание компанией пока не подтверждены.',
    'Trail footwear, rain and cold protection, water and food. Check weather, '
    'trail access and personal fitness before departure. Overnight stays, guiding, '
    'transport and meals have not been confirmed by our company.',
    'Wanderschuhe, Regen- und Kälteschutz, Wasser und Verpflegung. Wetter, '
    'Wegzugang und eigene Kondition vorher prüfen. Übernachtung, Führung, '
    'Transport und Verpflegung sind von unserem Unternehmen noch nicht bestätigt.',
    '请准备徒步鞋、防雨保暖衣物、饮水和食品。出发前确认天气、路线开放情况和身体条件。'
    '本公司的住宿、向导、交通和餐饮服务尚未确认。',
)


def itinerary(
    key,
    title_ru,
    title_en,
    region,
    season,
    difficulty,
    stages,
    sources,
    *,
    distance=None,
    altitude=None,
    notes='',
    image=None,
):
    """Each stage is one walking day, not a transfer-only calendar day."""
    titles = names(title_ru, title_en)
    paths = [names(ru, en) for ru, en in stages]
    routes = {
        lang: '\n'.join(f'{i}. {path[lang]}' for i, path in enumerate(paths, 1))
        for lang in LANGUAGES
    }
    descriptions = {}
    for lang in LANGUAGES:
        descriptions[lang] = {
            'ru': f'Пеший маршрут: {titles[lang]}. Местоположение: {REGIONS[region][lang]}. '
            f'Продолжительность: {len(stages)} дн. Сезон: {SEASONS[season][lang]}. '
            f'Этапы:\n{routes[lang]}',
            'en': f'Walking itinerary: {titles[lang]}. Location: {REGIONS[region][lang]}. '
            f'Duration: {len(stages)} day(s). Season: {SEASONS[season][lang]}. '
            f'Stages:\n{routes[lang]}',
            'de': f'Wanderroute: {titles[lang]}. Region: {REGIONS[region][lang]}. '
            f'Dauer: {len(stages)} Tag(e). Saison: {SEASONS[season][lang]}. '
            f'Etappen:\n{routes[lang]}',
            'zh': f'徒步路线：{titles[lang]}。地区：{REGIONS[region][lang]}。'
            f'时长：{len(stages)}天。季节：{SEASONS[season][lang]}。'
            f'每日路线：\n{routes[lang]}',
        }[lang]
    content = {
        lang: dict(
            title=titles[lang],
            description=descriptions[lang],
            route=routes[lang],
            difficulty=DIFFICULTY[difficulty][lang],
            requirements=REQUIREMENTS[lang],
            included=None,
        )
        for lang in LANGUAGES
    }
    return dict(
        key=key,
        checked_on=CHECKED_ON,
        content=content,
        duration_days=len(stages),
        duration_hours=None,
        distance_km=distance,
        max_altitude=altitude,
        price=None,
        price_unit=None,
        is_active=False,
        main_image=None,
        min_people=None,
        max_people=None,
        programs=[
            dict(
                day_number=i,
                start_time=None,
                end_time=None,
                content={
                    lang: dict(title=path[lang], description=path[lang]) for lang in LANGUAGES
                },
            )
            for i, path in enumerate(paths, 1)
        ],
        sources=sources,
        review_notes=notes,
        image_key=image,
        missing_company_fields=[
            'price',
            'price_unit',
            'included',
            'group_limits',
            'confirmed_services_and_departures',
        ],
    )


ROUTES = [
    itinerary(
        'ala-kul-keldike-4d',
        'Каракольское ущелье — Ала-Куль — Алтын-Арашан — Ак-Суу',
        'Karakol Gorge — Ala-Kul — Altyn-Arashan — Ak-Suu',
        'karakol',
        'jun-sep',
        'medium',
        [
            (
                'Первый мост Каракольского ущелья — Кургактор — приют Сирота',
                'First bridge in Karakol Gorge — Kurgaktor — Sirota Hut',
            ),
            (
                'Приют Сирота — озеро Ала-Куль — перевал Ала-Куль — Кельдике',
                'Sirota Hut — Ala-Kul Lake — Ala-Kul Pass — Keldike',
            ),
            ('Кельдике — Алтын-Арашан', 'Keldike — Altyn-Arashan'),
            (
                'Алтын-Арашан — нижняя часть долины Арашан у Ак-Суу',
                'Altyn-Arashan — lower Arashan Valley near Ak-Suu',
            ),
        ],
        [DK + 'the-pearl-ala-kul-lake/'],
        image='ala-kul',
        notes='В заголовке дня 1 источника ошибочно указаны Жети-Огуз/Телеты; '
        'выбран вариант из текста дня через Сироту. Сумма этапов не совпадает '
        'с общим километражем; distance_km и max_altitude не заполнены.',
    ),
    itinerary(
        'jeti-oguz-ala-kul-5d',
        'Жети-Огуз — Телеты — Ала-Куль — Алтын-Арашан — Ак-Суу',
        'Jeti-Oguz — Telety — Ala-Kul — Altyn-Arashan — Ak-Suu',
        'karakol',
        'jun-sep',
        'medium',
        [
            (
                'Начало тропы к Телеты в Жети-Огузе — лагерь под перевалом Телеты',
                'Telety trailhead in Jeti-Oguz — camp below Telety Pass',
            ),
            (
                'Перевал Телеты — восточная долина Телеты — Каракольский альплагерь',
                'Telety Pass — East Telety Valley — Karakol Alp Camp',
            ),
            (
                'Каракольский альплагерь — Ала-Куль — перевал Ала-Куль — Кельдике',
                'Karakol Alp Camp — Ala-Kul — Ala-Kul Pass — Keldike',
            ),
            ('Кельдике — Алтын-Арашан', 'Keldike — Altyn-Arashan'),
            ('Алтын-Арашан — долина Арашан — Ак-Суу', 'Altyn-Arashan — Arashan Valley — Ak-Suu'),
        ],
        [DK + 'celestial-mountains/'],
        image='ala-kul',
        notes='Выбран пятидневный вариант, без конных участков. Сумма дневных '
        'расстояний отличается от итога источника; точные цифры опущены.',
    ),
    itinerary(
        'archa-tor-3d',
        'Чон-Кызыл-Суу — Кашка-Тор — Арча-Тор — Жети-Огуз',
        'Chon-Kyzyl-Suu — Kashka-Tor — Archa-Tor — Jeti-Oguz',
        'karakol',
        'jun-oct',
        'medium',
        [
            (
                'Пеший старт в Чон-Кызыл-Суу — долина Кашка-Тор',
                'Chon-Kyzyl-Suu trailhead — Kashka-Tor Valley',
            ),
            (
                'Кашка-Тор — перевал Арча-Тор — верхняя долина Жети-Огуз',
                'Kashka-Tor — Archa-Tor Pass — upper Jeti-Oguz Valley',
            ),
            (
                'Верхняя долина Жети-Огуз — юрточная поляна — водопад Жети-Огуз',
                'Upper Jeti-Oguz Valley — yurt meadow — Jeti-Oguz waterfall',
            ),
        ],
        [DK + 'archa-tor-pass/'],
        altitude=3800,
        notes='В источнике общий путь 25 км, дневные этапы дают 26 км: distance_km '
        'оставлено пустым. После пешего финиша оператор описывает автотрансфер '
        'в Каракол; он не обещается как услуга нашей компании.',
    ),
    itinerary(
        'karakol-radial-4d',
        'Каракольский альплагерь: подножие пика Каракол и Ала-Куль',
        'Karakol Alp Camp: Karakol Peak foot and Ala-Kul',
        'karakol',
        'jun-oct',
        'conflicting',
        [
            (
                'Первый мост Каракольского ущелья — Каракольский альплагерь',
                'First bridge in Karakol Gorge — Karakol Alp Camp',
            ),
            (
                'Каракольский альплагерь — подножие пика Каракол — альплагерь',
                'Karakol Alp Camp — foot of Karakol Peak — Alp Camp',
            ),
            (
                'Каракольский альплагерь — озеро Ала-Куль — альплагерь',
                'Karakol Alp Camp — Ala-Kul Lake — Alp Camp',
            ),
            (
                'Каракольский альплагерь — начало тропы у первого моста',
                'Karakol Alp Camp — trailhead near the first bridge',
            ),
        ],
        ['https://visitkarakol.com/radialtrekkings'],
        distance='49.00',
        image='ala-kul',
        notes='49 км — явно указанная пешая часть, не 63 км с транспортом. '
        'Источник одновременно называет маршрут подходящим начинающим и '
        'требующим опыта; сложность оставлена на уточнение. Восхождения на пик нет.',
    ),
    itinerary(
        'jyrgalan-turnaluu-1d',
        'Жыргалан — озеро Турналуу-Кёль — Жыргалан',
        'Jyrgalan — Turnaluu-Kol Lake — Jyrgalan',
        'jyrgalan',
        'jun-sep',
        'easy',
        [
            (
                'Жыргалан — озеро Турналуу-Кёль — панорамы долины — Жыргалан',
                'Jyrgalan — Turnaluu-Kol Lake — valley viewpoints — Jyrgalan',
            )
        ],
        [JY],
        distance='13.30',
        altitude=2862,
        notes='Выбран пеший Lake Panorama 13.3 км; не конный маршрут 12 км.',
    ),
    itinerary(
        'jyrgalan-kok-bel-1d',
        'Жыргалан — водопад Кок-Бель — Жыргалан',
        'Jyrgalan — Kok-Bel Waterfall — Jyrgalan',
        'jyrgalan',
        'may-oct',
        'easy',
        [
            (
                'Жыргалан — восточные пастбища — узкий каньон — Кок-Бель — Жыргалан',
                'Jyrgalan — eastern pastures — narrow canyon — Kok-Bel — Jyrgalan',
            )
        ],
        [JY],
        distance='12.00',
        altitude=2659,
    ),
    itinerary(
        'jyrgalan-uuru-tor-1d',
        'Жыргалан — Эки-Чат — Ууру-Тор — панорамный гребень — Жыргалан',
        'Jyrgalan — Eki-Chat — Uuru-Tor — panorama ridge — Jyrgalan',
        'jyrgalan',
        'jun-sep',
        'medium',
        [
            (
                'Жыргалан — Эки-Чат — Ууру-Тор — панорамный гребень — Жыргалан',
                'Jyrgalan — Eki-Chat — Uuru-Tor — panorama ridge — Jyrgalan',
            )
        ],
        [JY],
        distance='19.00',
        altitude=3117,
        notes='Пешая Robber’s Canyon loop. Название Emil’s Peak не переименовано '
        'в Tuzdun Bashy: у пешего и конного описаний различается номенклатура.',
    ),
    itinerary(
        'kyzart-song-kol-2d',
        'Кызарт — Чаарарча — Килемче — Бучук — Сон-Куль',
        'Kyzart — Chaararcha — Kilemche — Buchuk — Song-Kol',
        'songkol',
        'jun-aug',
        'medium',
        [
            ('Кызарт — перевал Чаарарча — Килемче', 'Kyzart — Chaararcha Pass — Kilemche'),
            ('Килемче — перевал Бучук — берег Сон-Куля', 'Kilemche — Buchuk Pass — Song-Kol shore'),
        ],
        ['https://www.tuk.kg/tours/song-kol-trekking-trip'],
        distance='26.00',
        notes='Только пеший двухдневный вариант ТУК, не конный тур. '
        'Июнь–август — сезон выбранной программы, а не доступные даты компании.',
    ),
    itinerary(
        'kol-ukok-kol-tor-2d',
        'Тропа Кол-Укок — Кол-Укок — Кол-Тор — возврат к тропе',
        'Kol-Ukok trailhead — Kol-Ukok — Kol-Tor — trailhead',
        'kochkor',
        'jun-sep',
        'medium',
        [
            (
                'Автомобильный конец подъездной дороги в ущелье Кол-Укок — озеро Кол-Укок',
                'Road-end trailhead in Kol-Ukok Gorge — Kol-Ukok Lake',
            ),
            (
                'Кол-Укок — радиальный выход к Кол-Тору — спуск к месту старта',
                'Kol-Ukok — side hike to Kol-Tor — descent to the trailhead',
            ),
        ],
        [
            'https://www.tuk.kg/tours/kol-ukok-kol-tor-lakes',
            'https://www.intourists.kg/en/tours/kol-tor-and-kol-ukok-lakes',
        ],
        distance='24.00',
        notes='Точный GPS автомобильной высадки в источниках не опубликован; '
        'не подменять его селом Исаакеев из другого варианта. '
        'Высоты начала и наборы в источниках расходятся; max_altitude пусто.',
    ),
    itinerary(
        'belogorka-1d',
        'Конец дороги в ущелье Сокулук — водопад Белогорка — возврат',
        'Sokuluk Gorge road end — Belogorka Waterfall — return',
        'chuy',
        'jun-aug',
        'medium',
        [
            (
                'Конец дороги в ущелье Сокулук — Белогорский водопад — место старта',
                'Sokuluk Gorge road end — Belogorka Waterfall — trailhead',
            )
        ],
        [
            'https://kyrgyzconcept.kg/tours/inbounds/106/',
            'https://tour.too.kg/tur-vodopad-belogorka',
        ],
        notes='Высоты 2100/2200 м и время у разных операторов различаются. '
        'duration_hours и max_altitude не заполняются; 1 день — без обещания расписания.',
    ),
    itinerary(
        'ak-sai-waterfall-1d',
        'Альплагерь Ала-Арча — Разбитое сердце — Ак-Сай — возврат',
        'Ala-Archa Alplager — Broken Heart — Ak-Sai Waterfall — return',
        'chuy',
        'jun-sep',
        'medium',
        [
            (
                'Альплагерь Ала-Арча — скала Разбитое сердце — водопад Ак-Сай — альплагерь',
                'Ala-Archa Alplager — Broken Heart rock — Ak-Sai Waterfall — Alplager',
            )
        ],
        [
            'https://concept.kg/tours/inbounds/to_pdf/63/',
            PARK,
            'https://bookit.kg/en/kyrgyzstan/bishkek-chuy/ak-sai-waterfall-ratsek',
        ],
        notes='Источники дают диапазоны расстояний и высот. Точные числовые поля пусты. '
        'Перед выходом уточнить актуальное начало тропы из-за изменений инфраструктуры.',
        image='ak-sai',
    ),
    itinerary(
        'ratsek-hut-2d',
        'Альплагерь Ала-Арча — хижина Рацека — альплагерь',
        'Ala-Archa Alplager — Ratsek Hut — Alplager',
        'chuy',
        'jun-sep',
        'hard',
        [
            (
                'Альплагерь Ала-Арча — Разбитое сердце — водопад Ак-Сай — хижина Рацека',
                'Ala-Archa Alplager — Broken Heart — Ak-Sai Waterfall — Ratsek Hut',
            ),
            (
                'Хижина Рацека — тропа Ак-Сай — альплагерь Ала-Арча',
                'Ratsek Hut — Ak-Sai trail — Ala-Archa Alplager',
            ),
        ],
        [
            'https://travelhub.kg/partners/doctourkyrgyz/tours/ratsek-hut',
            PARK,
            'https://bookit.kg/en/kyrgyzstan/bishkek-chuy/ak-sai-waterfall-ratsek',
        ],
        notes='Выбран летний двухдневный вариант с ночёвкой, не однодневный рывок. '
        'Выход на ледник и восхождения не входят в пеший маршрут. '
        'Ночёвка компанией не подтверждена; высоты в источниках даны диапазоном.',
        image='ak-sai',
    ),
    itinerary(
        'kegeti-kol-tor-1d',
        'Начало тропы в Кегеты — озеро Көл-Төр — возврат',
        'Kegeti trailhead — Kol-Tor Lake — return',
        'chuy',
        'jun-oct',
        'medium',
        [
            (
                'Начало тропы Кол-Тор в ущелье Кегеты — озеро Көл-Төр — та же точка старта',
                'Kol-Tor trailhead in Kegeti Gorge — Kol-Tor Lake — same trailhead',
            )
        ],
        [
            'https://travelhub.kg/tours/kegeti-kol-tor',
            'https://needguide.net/view_tour.php?tour_id=38461',
        ],
        notes='Не путать с Кол-Тором над Кол-Укоком в Нарынской области. '
        'Опубликованный километраж неодинаков у разных вариантов; оставлен пустым.',
    ),
    itinerary(
        'konorchek-central-1d',
        'Главный вход Конорчека — центральный амфитеатр — возврат',
        'Konorchek main entrance — central amphitheatre — return',
        'boom',
        'spring-autumn',
        'medium',
        [
            (
                'Парковка у указателя перед Красным мостом — главный вход — '
                'центральная площадь каньона — возврат к парковке',
                'Signed car park before the Red Bridge — main entrance — '
                'central canyon amphitheatre — return to car park',
            )
        ],
        [
            'https://hiking.kg/ru/chuy/konorchek',
            'https://kyrgyzconcept.kg/tours/inbounds/86/',
            'https://www.xtravel.kg/ru/blog/kanony-konorchek-krasnye-skaly-boomskogo-uschelya-po-doroge-na-issyk-kul',
        ],
        notes='Выбран маршрут главного входа до центральной площади. '
        'Не весь лабиринт и не короткая остановка у трассы. Уровень 3/5 '
        'hiking.kg; сезон — рекомендация xtravel. Не идти при угрозе ливней.',
    ),
    itinerary(
        'alamedin-teke-tor-1d',
        'Конец дороги у Тёплых Ключей — Теке-Төр — возврат',
        'Road end near Teplye Klyuchi — Teke-Tor Waterfall — return',
        'chuy',
        'late-spring',
        'medium',
        [
            (
                'Конец дороги выше Тёплых Ключей — тропа по Аламедину — '
                'водопад Теке-Төр — возврат к парковке',
                'Road end above Teplye Klyuchi — Alamedin trail — '
                'Teke-Tor Waterfall — return to car park',
            )
        ],
        [
            'https://peopletravel.kg/alamedinru',
            'https://www.intourists.kg/ru/tours/uschele-alamedin-pohod-do-vodopada-teke-tor',
            'https://soltoholidays.kg/ru/alamedin-gorge',
        ],
        notes='Сезон — рекомендация Solto Holidays; маршрут и длительность '
        'подтверждены местными операторами. Не включать термальные ванны как услугу.',
    ),
]

IMAGES = {
    'ala-kul': {
        'source': 'https://commons.wikimedia.org/wiki/File:Ala-Kul_lake.jpg',
        'author': 'Ekrem Canli',
        'license': 'CC BY-SA 3.0',
        'license_url': 'https://creativecommons.org/licenses/by-sa/3.0/',
        'subject': 'Ala-Kul Lake south of Karakol, Kyrgyzstan',
        'commons_file': 'Ala-Kul lake.jpg',
        'download_url': 'https://upload.wikimedia.org/wikipedia/commons/1/1d/Ala-Kul_lake.jpg',
        'sha1': 'd4ec839acc93f88801e521f9d867f2a69a0f79b4',
        'changes': 'None; original file',
        'checked_on': CHECKED_ON,
    },
    'ak-sai': {
        'source': 'https://commons.wikimedia.org/wiki/File:Ala_Archa_waterfall_01.jpg',
        'author': 'Davide Mauro',
        'license': 'CC BY-SA 4.0',
        'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
        'subject': 'Ak-Sai waterfall, Ala-Archa National Park, Kyrgyzstan',
        'commons_file': 'Ala Archa waterfall 01.jpg',
        'download_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f9/Ala_Archa_waterfall_01.jpg',
        'sha1': '6a02e5af3af004ef55a47319dd8b5205564350d6',
        'changes': 'None; original file',
        'checked_on': CHECKED_ON,
    },
}
