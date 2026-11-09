"""Add-only, local PostgreSQL importer for the reviewed Trekking catalogue."""

import argparse
import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from scripts.trekking_data import IMAGES, LANGUAGES, ROUTES

ROOT = Path(__file__).resolve().parents[1]
BATCH = 'kyrgyzgo-trekking-researched-2026-11-09'


def validate_target(raw_url, expected_database):
    """Reject remote, test, production-labelled and unexpected databases."""
    url = make_url(raw_url)
    name = url.database or ''
    if (
        url.get_backend_name() != 'postgresql'
        or url.host not in {'localhost', '127.0.0.1', '::1'}
        or name != expected_database
        or any(token in name.casefold() for token in ('test', 'pytest', 'prod', 'stage'))
        or set(url.query) & {'host', 'hostaddr', 'service'}
    ):
        raise ValueError('Import refused: expected the named local project PostgreSQL database')
    return url


def normalized(value):
    return re.sub(r'\W+', '', (value or '').casefold().replace('ё', 'е'))


def validate_commercial(value):
    """An empty/zero placeholder is not evidence of a company-approved price."""
    if not isinstance(value, dict):
        raise ValueError('Missing company-approved commercial data')
    estimate = value.get('is_estimate') is True and value.get('authorized_estimate') is True
    if value.get('approved_by_company') is not True and not estimate:
        raise ValueError('Missing company-approved commercial data')
    if estimate and (
        value.get('currency') != 'KGS'
        or not value.get('sources')
        or not value.get('checked_on')
        or not value.get('basis')
        or value.get('group_assumption')
        not in {'private_four_adults', 'joining_group_size_unpublished'}
    ):
        raise ValueError('Estimate requires currency, dated sources, basis and group assumption')
    try:
        price = Decimal(str(value['price']))
    except (KeyError, ValueError, InvalidOperation):
        raise ValueError('Missing company price') from None
    if not price.is_finite() or price <= 0 or price >= Decimal('10000000000'):
        raise ValueError('Company price must be positive and fit Numeric(12,2)')
    if price != price.quantize(Decimal('0.01')):
        raise ValueError('Company price must have at most two decimal places')
    # Match existing ORM defaults; these are not additional required user inputs.
    price_unit = value.get('price_unit', 'per_person')
    minimum = value.get('min_people', 1)
    if price_unit not in {'per_person', 'per_day', 'per_night', 'per_hour', 'per_trip'}:
        raise ValueError('Missing company-approved price unit')
    if type(minimum) is not int or not 1 <= minimum <= 2_147_483_647:
        raise ValueError('Invalid minimum group size')
    maximum = value.get('max_people')
    if maximum is not None and (
        type(maximum) is not int or not minimum <= maximum <= 2_147_483_647
    ):
        raise ValueError('Invalid maximum group size')
    return dict(price=price, price_unit=price_unit, min_people=minimum, max_people=maximum)


def estimate_note(pricing, lang):
    amount = pricing['price']
    private = pricing['group_assumption'] == 'private_four_adults'
    assumptions = {
        'ru': 'группа из четырёх взрослых'
        if private
        else 'участие в наборной группе; размер группы источником не указан',
        'en': 'four adults in a private group'
        if private
        else 'joining a shared group; source does not state group size',
        'de': 'Privatgruppe mit vier Erwachsenen'
        if private
        else 'Teilnahme an einer Sammelgruppe; Gruppengröße nicht veröffentlicht',
        'zh': '四名成人的私人团体' if private else '参加拼团；来源未公布团体人数',
    }
    return {
        'ru': f'Ориентировочная стоимость. Итоговая цена и состав услуг уточняются у менеджера. '
        f'Оценка: {amount} KGS за человека за весь маршрут. Допущение: {assumptions[lang]}. '
        'Гид, транспорт, питание и ночёвки учтены как бюджетный сценарий, '
        'а не как подтверждённые услуги нашей компании.',
        'en': f'Estimated cost. The final price and included services must be confirmed with the manager. '
        f'Estimate: {amount} KGS per person for the entire itinerary. Assumption: {assumptions[lang]}. '
        'Guide, transport, meals and overnight stays are budget assumptions, not confirmed company inclusions.',
        'de': f'Ungefährer Preis. Endpreis und Leistungsumfang sind mit dem Manager abzuklären. '
        f'Schätzung: {amount} KGS pro Person für die gesamte Route. Annahme: {assumptions[lang]}. '
        'Führung, Transport, Verpflegung und Übernachtungen sind Budgetannahmen, keine bestätigten Firmenleistungen.',
        'zh': f'参考费用。最终价格和服务内容请向经理确认。整条路线每人预计 {amount} KGS。'
        f'估算前提：{assumptions[lang]}。向导、交通、餐饮和住宿仅作为预算假设，'
        '并非本公司已确认提供的服务。',
    }[lang]


def record_values(route, pricing=None):
    """Use existing manual-translation hashes and the existing translations JSON."""
    from mysite.translations.content import mark_manual_translations

    source = dict(route['content']['ru'])
    translated = {lang: dict(route['content'][lang]) for lang in ('en', 'de', 'zh')}
    if pricing and pricing.get('is_estimate'):
        source['description'] += '\n\n' + estimate_note(pricing, 'ru')
        for lang, values in translated.items():
            values['description'] += '\n\n' + estimate_note(pricing, lang)
    source['description'] += '\n\n' + '\n'.join(route['sources'])
    for lang in translated:
        translated[lang]['description'] += '\n\n' + '\n'.join(route['sources'])
    image = IMAGES.get(route['image_key'])
    if image:
        credit = (
            f'Photo: {image["author"]} / {image["license"]}; {image["source"]}; '
            f'{image["license_url"]}; {image["changes"]}'
        )
        source['description'] += '\n\n' + credit
        for values in translated.values():
            values['description'] += '\n\n' + credit
    translations = mark_manual_translations(translated, source)
    translations['_trekking_import'] = {
        'batch': BATCH,
        'key': route['key'],
        'sources': route['sources'],
        'checked_on': route['checked_on'],
        'review_notes': route['review_notes'],
        'image': image,
        'price_estimate': pricing if pricing and pricing.get('is_estimate') else None,
    }
    return dict(
        **source,
        translations=translations,
        duration_days=route['duration_days'],
        duration_hours=route['duration_hours'],
        distance_km=route['distance_km'],
        max_altitude=route['max_altitude'],
        main_image=image['download_url'] if image else None,
        is_active=False,
    )


def find_existing(rows, route):
    for row in rows:
        metadata = (row.translations or {}).get('_trekking_import', {})
        if metadata.get('batch') == BATCH and metadata.get('key') == route['key']:
            return row
        if normalized(row.title) == normalized(route['content']['ru']['title']):
            return row
        if row.duration_days == route['duration_days'] and normalized(row.route) == normalized(
            route['content']['ru']['route']
        ):
            return row
        aliases = {
            'ak-sai-waterfall-1d': 'Тропа к водопаду Ак-Сай',
            'kegeti-kol-tor-1d': 'Тропа к озеру Коль-Тор',
        }
        if row.duration_days == route['duration_days'] and normalized(row.title) == normalized(
            aliases.get(route['key'], '')
        ):
            return row
    return None


def import_rows(db, commercial, *, apply=False):
    from mysite.database.models import Trekking, TrekkingImage, TrekkingProgram
    from mysite.translations.content import mark_manual_translations

    if apply:
        # Serialize concurrent imports, without adding a table or touching existing rows.
        db.execute(text('SELECT pg_advisory_xact_lock(71931604211109)'))
    rows = list(db.scalars(select(Trekking)))
    pending, result = [], []
    for route in ROUTES:
        existing = find_existing(rows, route)
        if existing:
            result.append(dict(key=route['key'], id=existing.id, status='existing_untouched'))
            continue
        try:
            price = validate_commercial(commercial.get(route['key']))
        except ValueError as error:
            result.append(dict(key=route['key'], id=None, status='blocked', reason=str(error)))
            continue
        pending.append((route, price))
    blocked = any(item['status'] == 'blocked' for item in result)
    if not apply or blocked:
        result.extend(
            dict(key=route['key'], id=None, status='ready_not_written') for route, _ in pending
        )
        return result
    for route, price in pending:
        row = Trekking(**record_values(route, commercial.get(route['key'])), **price)
        for program in route['programs']:
            source = program['content']['ru']
            translations = mark_manual_translations(
                {lang: program['content'][lang] for lang in ('en', 'de', 'zh')}, source
            )
            row.programs.append(
                TrekkingProgram(
                    **source, day_number=program['day_number'], translations=translations
                )
            )
        image = IMAGES.get(route['image_key'])
        if image:
            row.images.append(TrekkingImage(image=image['download_url'], order=0))
        db.add(row)
        db.flush()
        result.append(dict(key=route['key'], id=row.id, status='created_draft'))
    # Caller commits all new parents/programs/images in one transaction.
    return result


def api_probe(engine, identities):
    """No lifespan: do not recover translation jobs in unrelated sections."""
    from fastapi.testclient import TestClient

    from main import app
    from mysite.database.db import get_db
    from mysite.database.models import Trekking

    def local_session():
        with Session(engine) as db:
            db.execute(text('SET TRANSACTION READ ONLY'))
            yield db

    before = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = local_session
    try:
        http = TestClient(app)
        result = {}
        for path in ('/trekkings/', '/trekking-programs/', '/trekking-images/'):
            response = http.get(path)
            result[path] = response.status_code
            if response.status_code != 200:
                raise RuntimeError('Local Trekking read API failed: ' + path)
        for identity in identities:
            with Session(engine) as db:
                active = db.get(Trekking, identity).is_active
            expected = 200 if active else 404
            for lang in LANGUAGES:
                path = f'/trekkings/{identity}/?lang={lang}'
                response = http.get(path)
                result[path] = response.status_code
                if response.status_code != expected:
                    raise RuntimeError('Unexpected Trekking detail visibility')
            for resource in ('trekking-programs', 'trekking-images'):
                path = f'/{resource}/?trekking_id={identity}'
                response = http.get(path)
                result[path] = response.status_code
                if response.status_code != expected:
                    raise RuntimeError('Unexpected Trekking child visibility')
                if active and any(item['trekking_id'] != identity for item in response.json()):
                    raise RuntimeError('Trekking child belongs to another parent')
        return result
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(before)


def snapshot(engine, *, through_ids=None):
    """Content fingerprints without displaying existing records or any secrets."""
    with engine.connect() as connection:
        values = {}
        for table in (
            'trekkings',
            'trekking_programs',
            'trekking_images',
            'tours',
            'hotels',
            'transports',
            'helicopter_tours',
            'tour_categories',
            'countries',
            'regions',
            'districts',
            'abouts',
            'about_sections',
            'contacts',
            'faqs',
        ):
            where = f' WHERE id <= {int(through_ids[table])}' if through_ids else ''
            values[table] = (
                connection.execute(
                    text(
                        f'SELECT count(*), md5(COALESCE(string_agg(row_to_json(t)::text, '
                        f"'' ORDER BY id), '')) FROM {table} t{where}"
                    )
                )
                .one()
                ._asdict()
            )
        return values


def admin_probe(engine, identities):
    """Use existing SQLAdmin detail loaders in-process, without creating logins."""
    import asyncio

    from sqlalchemy.orm import sessionmaker
    from starlette.requests import Request

    from mysite.admin.views import TrekkingAdmin, TrekkingImageAdmin, TrekkingProgramAdmin
    from mysite.translations.content import localized

    async def inspect_records():
        views = [TrekkingAdmin(), TrekkingProgramAdmin(), TrekkingImageAdmin()]
        for view in views:
            view.session_maker = sessionmaker(bind=engine)
            view.is_async = False
        records = []
        for identity in identities:
            request = Request({'type': 'http', 'path_params': {'pk': str(identity)}})
            row = await views[0].get_object_for_details(request)
            if row is None:
                raise RuntimeError('Record not readable through SQLAdmin')
            metadata = (row.translations or {}).get('_trekking_import', {})
            pricing = metadata.get('price_estimate')
            if not pricing:
                continue  # Legacy existing matches must remain untouched.
            if row.is_active:
                raise RuntimeError('Imported estimate was unexpectedly activated')
            for lang in LANGUAGES:
                description = localized(row, lang)['description']
                if estimate_note(pricing, lang) not in description:
                    raise RuntimeError('Estimate disclaimer missing or translation stale')
            for child, child_view in [
                *((p, views[1]) for p in row.programs),
                *((i, views[2]) for i in row.images),
            ]:
                child_request = Request({'type': 'http', 'path_params': {'pk': str(child.id)}})
                fetched = await child_view.get_object_for_details(child_request)
                if fetched is None or fetched.trekking_id != identity:
                    raise RuntimeError('Imported child is not readable through SQLAdmin')
            if len(row.programs) != row.duration_days:
                raise RuntimeError('Program duration mismatch')
            records.append(
                dict(
                    id=row.id,
                    key=metadata['key'],
                    title=row.title,
                    duration_days=row.duration_days,
                    price=str(row.price),
                    currency=pricing['currency'],
                    price_unit=row.price_unit.value,
                    is_active=row.is_active,
                    program_ids=[p.id for p in row.programs],
                    image_ids=[i.id for i in row.images],
                    translation_languages=list(LANGUAGES),
                    admin_read='SQLAdmin.get_object_for_details',
                )
            )
        return records

    return asyncio.run(inspect_records())


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-database', required=True)
    parser.add_argument('--commercial-data', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument(
        '--export', type=Path, default=ROOT / 'data/trekking/researched-routes.json'
    )
    parser.add_argument('--report', type=Path, default=ROOT / 'docs/trekking-import-result.json')
    args = parser.parse_args()
    url = validate_target(os.environ.get('DATABASE_URL', ''), args.expect_database)
    commercial = (
        json.loads(args.commercial_data.read_text(encoding='utf-8')) if args.commercial_data else {}
    )
    args.export.parent.mkdir(parents=True, exist_ok=True)
    args.export.write_text(
        json.dumps(dict(routes=ROUTES, images=IMAGES), ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    engine = create_engine(url, connect_args={'connect_timeout': 5})
    try:
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT current_database()')) == args.expect_database
            address = connection.scalar(text('SELECT inet_server_addr()::text'))
            if address not in {'127.0.0.1/32', '::1/128'}:
                raise ValueError('Server address is not loopback; import refused')
        before = snapshot(engine)
        with engine.connect() as connection:
            through_ids = {
                table: connection.scalar(text(f'SELECT COALESCE(max(id), 0) FROM {table}'))
                for table in before
            }
        existing_before = snapshot(engine, through_ids=through_ids)
        price_column = next(
            c for c in inspect(engine).get_columns('trekkings') if c['name'] == 'price'
        )
        with Session(engine) as db:
            if not args.apply:
                db.execute(text('SET TRANSACTION READ ONLY'))
            results = import_rows(db, commercial, apply=args.apply)
            blocked = any(item['status'] == 'blocked' for item in results)
            if args.apply and not blocked:
                db.commit()
            else:
                db.rollback()
        created = [item['id'] for item in results if item['status'] == 'created_draft']
        api = api_probe(engine, [item['id'] for item in results if item['id'] is not None])
        admin_records = (
            admin_probe(engine, [item['id'] for item in results if item['id'] is not None])
            if commercial
            else []
        )
        after = snapshot(engine)
        existing_unchanged = existing_before == snapshot(engine, through_ids=through_ids)
        untouched = all(
            before[table] == after[table]
            for table in before
            if table not in {'trekkings', 'trekking_programs', 'trekking_images'}
        )
        if not untouched or not existing_unchanged or (not created and before != after):
            raise RuntimeError('Unexpected catalogue mutation detected')
        report = dict(
            environment='local PostgreSQL',
            host=url.host,
            database=url.database,
            price_nullable=price_column['nullable'],
            requested_apply=args.apply,
            results=results,
            api=api,
            admin_records=admin_records,
            created_count=len(created),
            non_trekking_catalogue_unchanged=untouched,
            preexisting_rows_unchanged=existing_unchanged,
            all_checked_rows_unchanged=before == after,
            snapshot_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if blocked else 0
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
