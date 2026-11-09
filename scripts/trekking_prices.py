"""Reproducible, user-authorized estimates; never confirmed company tariffs."""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CHECKED_ON = '2026-11-09'
USD_KGS = Decimal('87.4478')
FX_SOURCE = 'https://www.nbkr.kg/index1.jsp?item=1562&lang=ENG&valuta_id=15'
SOURCES = {
    'ala_budget': {
        'url': 'https://kyrgyz-tours.com/tour/ala-kul-lake-tour/',
        'observed': '4 days, group of 4: USD 340/person; guide, local transfers, camping, food.',
    },
    'ala_standard': {
        'url': 'https://ecotourism.kg/tours/ala-kul-lake-trekking-4-days',
        'observed': '4 days, group of 4: USD 530/person; guide, meals, local transfers, yurt night. Sleeping bags extra.',
    },
    'archa': {
        'url': 'https://hikingkyrgyzstan.com/best-hikes-in-kyrgyzstan/archa-tor-pass/',
        'observed': '3 days, group of 4: USD 620/person; transfers, camping kit, guide, porters/cook and food. Tariff undated.',
    },
    'jyrgalan_guide': {
        'url': 'https://www.travel-kyrgyzstan.com/tours/jyrgalan-skitouring-yurt-lodge/',
        'observed': 'Summer guided outings: guide supplement KGS 4000; guide-service comparator, not an exact hiking quotation.',
    },
    'jyrgalan_transfer': {
        'url': 'https://destinationkarakol.com/what-to-do/day-trips/',
        'observed': 'Private Karakol to Jyrgalan taxi: KGS 3500–4000/car one way.',
    },
    'food': {
        'url': 'https://jyrgalan.com/where-to-stay/salamat-guesthouse/',
        'observed': 'Picnic lunch KGS 350; lunch/dinner KGS 400. Regional food-budget comparator, not a catering contract.',
    },
    'songkol': {
        'url': 'https://www.tuk.kg/tours/song-kol-trekking-trip',
        'observed': '2-day group trek KGS 7000/person: transport, guide, yurt with breakfast, first dinner; trail meals extra.',
    },
    'kolukok_tuk': {
        'url': 'https://www.tuk.kg/tours/kol-ukok-kol-tor-lakes',
        'observed': '2-day group trek KGS 5000/person; transfers, guide, camping kit; meals extra.',
    },
    'kolukok_intourists': {
        'url': 'https://www.intourists.kg/en/tours/kol-tor-and-kol-ukok-lakes',
        'observed': '2-day group trek KGS 6000/person; transfers, guide, camping; meals extra.',
    },
    'belogorka': {
        'url': 'https://kyrgyzconcept.kg/tours/inbounds/106/',
        'observed': 'Group of 4: USD 59/person, guide and transport; lunch box USD 12 extra.',
    },
    'ratsek_comparator': {
        'url': 'https://www.tuk.kg/tours/peak-uchitel',
        'observed': '2-day Uchitel ascent KGS 5000/person, transfers, park entry, guide and Ratsek overnight/kit; meals extra. More demanding comparator, no ascent added to our itinerary.',
    },
    'konorchek': {
        'url': 'https://kyrgyzconcept.kg/tours/inbounds/86/',
        'observed': 'Burana + Konorchek day tour, group of 4: USD 67/person incl guide/car/entries; lunch USD 12 extra. Conservative upper comparator; Burana is not part of our walking itinerary.',
    },
    'alamedin': {
        'url': 'https://peopletravel.kg/alamedinru',
        'observed': '4+ people USD 45/person; local day tour with guide, transport and lunch.',
    },
    'jeti_sanity': {
        'url': 'https://kyrgyzguidedtours.com/en/product/trekking-to-ala-kol-lake-5-days/',
        'observed': '2026 detailed table USD 802/person at 4, but includes Bishkek transfers/hotels and only 3 trekking days. Headline USD 200 is inconsistent; neither used as an exact price for five walking days.',
    },
}


def rounded(value, step='100'):
    increment = Decimal(step)
    return (value / increment).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * increment


def estimates():
    result = {}

    def add(key, value, basis, sources, group=4, step='100'):
        result[key] = dict(
            price=str(rounded(value, step)),
            price_unit='per_person',
            currency='KGS',
            is_estimate=True,
            authorized_estimate=True,
            checked_on=CHECKED_ON,
            assumed_group_size=group,
            min_people=1,
            group_assumption='private_four_adults' if group else 'joining_group_size_unpublished',
            basis=basis,
            unrounded_kgs=str(value),
            rounding_kgs=step,
            source_ids=sources,
            sources=[SOURCES[name]['url'] for name in sources],
            usd_kgs=str(USD_KGS),
            fx_source=FX_SOURCE,
        )

    midpoint = (Decimal('340') + Decimal('530')) / 2
    add(
        'ala-kul-keldike-4d',
        midpoint * USD_KGS,
        'Mean of two 4-person, 4-day guided packages: (340+530)/2 USD. '
        'Budget scenario: local Karakol transfers, guide, basic camping/yurt and meals; no Bishkek travel.',
        ['ala_budget', 'ala_standard'],
        step='500',
    )
    add(
        'jeti-oguz-ala-kul-5d',
        midpoint * Decimal('5') / 4 * USD_KGS,
        '4-day private-package midpoint scaled to 5 walking days: 435*5/4 USD. '
        'Allows an extra guide/food/camp day. Not the unrelated 5-calendar-day Bishkek package.',
        ['ala_budget', 'ala_standard', 'jeti_sanity'],
        step='500',
    )
    add(
        'archa-tor-3d',
        (midpoint * Decimal('3') / 4 + Decimal('620')) / 2 * USD_KGS,
        'Mean of 3-day normalized regional package (435*3/4 USD) and published '
        'Archa-Tor full-support price (620 USD at four). Range reflects porter/cook and access differences.',
        ['ala_budget', 'ala_standard', 'archa'],
        step='500',
    )
    add(
        'karakol-radial-4d',
        midpoint * USD_KGS,
        'Same four guide-days and three basic camp nights as the 4-day Karakol-package '
        'comparators. No unsupported discount for a fixed camp; local transfers/food considered.',
        ['ala_budget', 'ala_standard'],
        step='500',
    )
    for key in ('jyrgalan-turnaluu-1d', 'jyrgalan-kok-bel-1d', 'jyrgalan-uuru-tor-1d'):
        add(
            key,
            Decimal('4000') / 4 + Decimal('4000') * 2 / 4 + Decimal('350'),
            'Guide-service comparator 4000/group/day divided by four + two taxi legs '
            '4000/car divided by four + 350/person picnic. No overnight, horse or additional meals; '
            'same full-day guide booking for each loop.',
            ['jyrgalan_guide', 'jyrgalan_transfer', 'food'],
        )
    add(
        'kyzart-song-kol-2d',
        Decimal('7000') + 4 * Decimal('400'),
        'Published join-in package 7000 plus four meals budgeted at regional 400/meal; '
        'one dinner and one breakfast already in comparator. Not a private four-person quote.',
        ['songkol', 'food'],
        group=None,
    )
    add(
        'kol-ukok-kol-tor-2d',
        (Decimal('5000') + Decimal('6000')) / 2 + 6 * Decimal('400'),
        'Mean of two join-in guided camping packages plus six meals at 400/meal. '
        'Transport/camping already in anchors; no extra yurt dinner or private-group premium claimed.',
        ['kolukok_tuk', 'kolukok_intourists', 'food'],
        group=None,
    )
    add(
        'belogorka-1d',
        (Decimal('59') + Decimal('12')) * USD_KGS,
        'Published private four-person guide/vehicle rate 59 USD plus 12 USD lunch. No overnight.',
        ['belogorka'],
    )
    add(
        'ratsek-hut-2d',
        Decimal('5000') + 6 * Decimal('400'),
        'Conservative overnight-trip comparator 5000 includes guide, transfers and Ratsek hut/kit; '
        'add six meals at 400. Comparator summit is harder; no speculative deduction, '
        'and neither summit nor glacier services promised.',
        ['ratsek_comparator', 'food'],
        group=None,
    )
    add(
        'konorchek-central-1d',
        (Decimal('67') + Decimal('12')) * USD_KGS,
        'Conservative private four-person day-trip budget 67 USD plus lunch 12 USD. '
        'Comparator also visits Burana; no unsupported component deduction, Burana not added '
        'to the route or confirmed inclusions.',
        ['konorchek'],
    )
    add(
        'alamedin-teke-tor-1d',
        Decimal('45') * USD_KGS,
        'Published 4+ person analogue 45 USD includes guide, car and lunch. No overnight.',
        ['alamedin'],
    )
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / 'data/trekking'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'estimated-prices.json').write_text(
        json.dumps(estimates(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    (directory / 'price-sources.json').write_text(
        json.dumps(
            dict(checked_on=CHECKED_ON, sources=SOURCES, usd_kgs=str(USD_KGS), fx_source=FX_SOURCE),
            ensure_ascii=False,
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )
    print('Prepared 13 authorized estimates in KGS; no database writes.')


if __name__ == '__main__':
    main()
