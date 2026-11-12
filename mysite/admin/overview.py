from datetime import UTC, datetime, time, timedelta, timezone

from sqlalchemy import Date, cast, distinct, func, select

from mysite.database.chat_models import ChatClient, ChatMessage, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import (HelicopterTour, Hotel, RequestStatusChoices, Tour, Transport,
                                    TravelRequest, Trekking)
from mysite.database.selection_models import TravelSelection
from mysite.database.tour_review_models import TourReview

BISHKEK = timezone(timedelta(hours=6))
PERIODS = {'7': 7, '30': 30, '90': 90, 'all': None}
PERIOD_LABELS = {'7': '7 дней', '30': '30 дней', '90': '90 дней', 'all': 'Всё время'}
DEFAULT_PERIOD = '30'
MONTHS = ('янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек')
STATUSES = {
    RequestStatusChoices.new.value: ('Новая', 'blue'),
    RequestStatusChoices.in_progress.value: ('В работе', 'yellow'),
    RequestStatusChoices.completed.value: ('Завершена', 'green'),
    RequestStatusChoices.cancelled.value: ('Отменена', 'secondary'),
}
CATALOG = (
    ('tour', 'Туры', Tour),
    ('hotel', 'Отели', Hotel),
    ('transport', 'Транспорт', Transport),
    ('helicopter-tour', 'Вертолётные туры', HelicopterTour),
    ('trekking', 'Треккинг', Trekking),
)
WEEKLY_AFTER_DAYS = 92


def plural(number, forms):
    tail = abs(number) % 100
    if 10 < tail < 20:
        return forms[2]
    tail %= 10
    if tail == 1:
        return forms[0]
    if 2 <= tail <= 4:
        return forms[1]
    return forms[2]


def short_date(day):
    return f'{day.day} {MONTHS[day.month - 1]}'


def local_midnight(day):
    return datetime.combine(day, time.min, tzinfo=BISHKEK).astimezone(UTC)


def local_bucket(column, weekly):
    local = func.timezone('Asia/Bishkek', column)
    return cast(func.date_trunc('week', local) if weekly else local, Date)


def first_activity(db):
    dates = [
        db.scalar(select(func.min(ChatClient.created_at))),
        db.scalar(select(func.min(ChatMessage.created_at))),
        db.scalar(select(func.min(TravelRequest.created_at))),
    ]
    found = [value for value in dates if value is not None]
    return min(found).astimezone(BISHKEK).date() if found else None


class Window:
    def __init__(self, db, period, now):
        today = now.astimezone(BISHKEK).date()
        days = PERIODS[period]
        if days is None:
            self.first_day = first_activity(db) or today
            days = (today - self.first_day).days + 1
        else:
            self.first_day = today - timedelta(days=days - 1)
        self.days = days
        self.last_day = today
        self.start = local_midnight(self.first_day)
        self.end = local_midnight(today + timedelta(days=1))
        self.previous_start = None if PERIODS[period] is None else self.start - timedelta(days=days)
        self.weekly = days > WEEKLY_AFTER_DAYS

    def where(self, column, previous=False):
        if previous:
            return (column >= self.previous_start, column < self.start)
        return (column >= self.start, column < self.end)

    def buckets(self):
        if not self.weekly:
            return [self.first_day + timedelta(days=step) for step in range(self.days)]
        monday = self.first_day - timedelta(days=self.first_day.weekday())
        return [
            monday + timedelta(weeks=step) for step in range((self.last_day - monday).days // 7 + 1)
        ]


def nice_top(value):
    if value <= 4:
        return 4
    magnitude = 10 ** (len(str(value)) - 1)
    return next(step * magnitude for step in (2, 4, 6, 8, 10) if step * magnitude >= value)


def label_positions(count, labels):
    every = max(1, round(count / labels))
    last = count - 1
    marks = {index for index in range(0, count, every) if last - index >= every * 0.75}
    return marks | {last}


def chart(window, counts, forms, title, labels=6):
    buckets = window.buckets()
    values = [counts.get(bucket, 0) for bucket in buckets]
    top = nice_top(max(values, default=0))
    marks = label_positions(len(buckets), labels)
    points = []
    for index, (bucket, value) in enumerate(zip(buckets, values, strict=True)):
        if window.weekly:
            period_text = f'неделя с {short_date(bucket)}'
        else:
            period_text = short_date(bucket)
        points.append(
            {
                'height': round(value / top * 100, 2),
                'value': value,
                'tip': f'{period_text}: {value} {plural(value, forms)}',
                'label': short_date(bucket) if index in marks else '',
                'period': period_text,
            }
        )
    return {
        'title': title,
        'total': sum(values),
        'points': points,
        'ticks': [top, top // 2, 0],
        'empty': not any(values),
    }


def daily(db, window, column, *conditions):
    bucket = local_bucket(column, window.weekly).label('bucket')
    rows = db.execute(
        select(bucket, func.count()).where(*window.where(column), *conditions).group_by(bucket.name)
    ).all()
    return {day: count for day, count in rows}


def change(current, previous):
    if previous is None:
        return None
    difference = current - previous
    if difference == 0:
        return {'direction': 'same', 'text': 'столько же, сколько в прошлом периоде'}
    sign = '+' if difference > 0 else '−'
    return {
        'direction': 'up' if difference > 0 else 'down',
        'text': f'{sign}{abs(difference)} к прошлому периоду',
    }


def ai_users(db, conditions):
    return db.scalar(
        select(func.count(distinct(ChatSession.client_id)))
        .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatMessage.role == 'user', *conditions)
    )


def kpis(db, window):
    previous = window.previous_start is not None

    def pair(build):
        current = build(False)
        return current, build(True) if previous else None

    clients = pair(
        lambda old: db.scalar(
            select(func.count(ChatClient.id)).where(*window.where(ChatClient.created_at, old))
        )
    )
    users = pair(lambda old: ai_users(db, window.where(ChatMessage.created_at, old)))
    questions = pair(
        lambda old: db.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.role == 'user', *window.where(ChatMessage.created_at, old)
            )
        )
    )
    requests = pair(
        lambda old: db.scalar(
            select(func.count(TravelRequest.id)).where(*window.where(TravelRequest.created_at, old))
        )
    )
    total_clients = db.scalar(select(func.count(ChatClient.id)))
    waiting = db.scalar(
        select(func.count(TravelRequest.id)).where(TravelRequest.status == RequestStatusChoices.new)
    )
    per_day = questions[0] / window.days
    return [
        {
            'key': 'clients',
            'icon': 'fa-solid fa-user-plus',
            'label': 'Новые клиенты',
            'value': clients[0],
            'change': change(*clients),
            'note': f'всего {total_clients} {plural(total_clients, ("клиент", "клиента", "клиентов"))}',
        },
        {
            'key': 'ai-users',
            'icon': 'fa-solid fa-comments',
            'label': 'Общались с ИИ',
            'value': users[0],
            'change': change(*users),
            'note': f'из {total_clients} зарегистрированных',
        },
        {
            'key': 'questions',
            'icon': 'fa-solid fa-robot',
            'label': 'Вопросов к ИИ',
            'value': questions[0],
            'change': change(*questions),
            'note': f'в среднем {per_day:.1f} в день'.replace('.', ','),
        },
        {
            'key': 'requests',
            'icon': 'fa-solid fa-paper-plane',
            'label': 'Заявки',
            'value': requests[0],
            'change': change(*requests),
            'note': f'ждут ответа: {waiting}',
            'alert': waiting > 0,
        },
    ]


def funnel(db, window):
    cohort = select(ChatClient.id).where(*window.where(ChatClient.created_at))
    registered = db.scalar(select(func.count()).select_from(cohort.subquery()))
    steps = [
        ('Зарегистрировались', registered),
        ('Написали ИИ-помощнику', ai_users(db, (ChatSession.client_id.in_(cohort),))),
        (
            'Собрали подборку',
            db.scalar(
                select(func.count(distinct(TravelSelection.client_id))).where(
                    TravelSelection.client_id.in_(cohort)
                )
            ),
        ),
        (
            'Отправили заявку',
            db.scalar(
                select(func.count(distinct(TravelRequest.client_id))).where(
                    TravelRequest.client_id.in_(cohort)
                )
            ),
        ),
    ]
    return [
        {
            'label': label,
            'value': value,
            'width': round(value / registered * 100, 2) if registered else 0,
            'share': f'{round(value / registered * 100)}%' if registered else '-',
        }
        for label, value in steps
    ]


def interests(db, window):
    found = []
    for kind, column, model, name in (
        ('Тур', TravelSelection.tour_id, Tour, Tour.title),
        ('Отель', TravelSelection.hotel_id, Hotel, Hotel.name),
        ('Транспорт', TravelSelection.transport_id, Transport, Transport.name),
    ):
        rows = db.execute(
            select(name, func.count(TravelSelection.id))
            .join(model, model.id == column)
            .where(*window.where(TravelSelection.created_at))
            .group_by(model.id, name)
        ).all()
        found.extend({'kind': kind, 'name': title, 'value': count} for title, count in rows)
    found.sort(key=lambda item: (-item['value'], item['name']))
    top = found[:6]
    biggest = max((item['value'] for item in top), default=0)
    for item in top:
        item['width'] = round(item['value'] / biggest * 100, 2) if biggest else 0
    return top


def request_statuses(db, window):
    rows = dict(
        db.execute(
            select(TravelRequest.status, func.count(TravelRequest.id))
            .where(*window.where(TravelRequest.created_at))
            .group_by(TravelRequest.status)
        ).all()
    )
    counts = {getattr(status, 'value', status): count for status, count in rows.items()}
    return [
        {'label': label, 'color': color, 'value': counts.get(status, 0)}
        for status, (label, color) in STATUSES.items()
    ]


def latest_requests(db):
    rows = db.scalars(
        select(TravelRequest).order_by(TravelRequest.created_at.desc()).limit(6)
    ).all()
    result = []
    for row in rows:
        status = getattr(row.status, 'value', row.status)
        label, color = STATUSES.get(status, (status, 'secondary'))
        created = row.created_at.astimezone(BISHKEK) if row.created_at else None
        result.append(
            {
                'id': row.id,
                'name': row.name,
                'destination': row.destination or '-',
                'travel_date': row.travel_date.strftime('%d.%m.%Y') if row.travel_date else '-',
                'created': f'{short_date(created.date())}, {created:%H:%M}' if created else '-',
                'source': 'чат' if row.source == 'chat' else 'сайт',
                'status': label,
                'color': color,
            }
        )
    return result


def catalog(db):
    result = []
    for identity, label, model in CATALOG:
        active, hidden = db.execute(
            select(
                func.count(model.id).filter(model.is_active.is_(True)),
                func.count(model.id).filter(model.is_active.is_not(True)),
            )
        ).one()
        result.append({'identity': identity, 'label': label, 'active': active, 'hidden': hidden})
    return result


def reviews(db):
    count, average = db.execute(
        select(func.count(TourReview.id), func.avg(TourReview.rating))
    ).one()
    return {
        'count': count,
        'average': f'{average:.1f}'.replace('.', ',') if average is not None else None,
        'forms': plural(count, ('отзыв', 'отзыва', 'отзывов')),
    }


def build_overview(period, show_requests, now=None):
    period = period if period in PERIODS else DEFAULT_PERIOD
    now = now or datetime.now(UTC)
    with SessionLocal() as db:
        window = Window(db, period, now)
        charts = [
            chart(
                window,
                daily(db, window, ChatMessage.created_at, ChatMessage.role == 'user'),
                ('вопрос', 'вопроса', 'вопросов'),
                'Вопросы ИИ-помощнику',
            ),
            chart(
                window,
                daily(db, window, ChatClient.created_at),
                ('регистрация', 'регистрации', 'регистраций'),
                'Новые клиенты',
                labels=4,
            ),
            chart(
                window,
                daily(db, window, TravelRequest.created_at),
                ('заявка', 'заявки', 'заявок'),
                'Заявки',
                labels=4,
            ),
        ]
        return {
            'period': period,
            'periods': PERIOD_LABELS,
            'range': f'{short_date(window.first_day)} - {short_date(window.last_day)} '
            f'{window.last_day.year}',
            'weekly': window.weekly,
            'kpis': kpis(db, window),
            'charts': charts,
            'funnel': funnel(db, window),
            'interests': interests(db, window),
            'statuses': request_statuses(db, window),
            'latest': latest_requests(db) if show_requests else None,
            'catalog': catalog(db),
            'reviews': reviews(db),
        }
