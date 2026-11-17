"""Check monetary claims against actual tool results, never client-supplied JSON."""

import re
from decimal import Decimal, InvalidOperation

_NUMBER = r'\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,2})?'
_CURRENCY = r'USD|EUR|KGS|RUB|GBP|CNY|доллар\w*|dollars?|сом\w*|евро|руб\w*|юан\w*|[$€£¥]'
_MONEY = re.compile(
    rf'(?P<amount>{_NUMBER})\s*(?P<currency>{_CURRENCY})(?!\w)'
    rf'|(?P<prefix>{_CURRENCY})\s*(?P<prefixed>{_NUMBER})',
    re.IGNORECASE,
)
# A bare number is a price only where the wording makes it one. "Вам стоит взять
# 2 куртки" and "цена в 2026 году" are not price claims; "цена: 80",
# "стоимость составляет 80", "стоит от 80" and "80 за человека" are.
_PRICE_NOUN = r'(?:цен[аы]|стоимость|стоимости|price|cost|preis|kosten|价格|费用|баасы|наркы)'
_PRICE_VERB = r'(?:стоит|стоят|costs?|kostet)'
_LINK = (
    r'(?:составляет|составит|равна|равен|будет|от|около|всего|лишь|только|'
    r'is|are|from|about|only|beträgt|ab|ca\.?|约|为)'
)
_PER = (
    r'(?:(?:за|на|с)[^\S\n]+(?:человека|чел\.?|персону|группу|компанию|поездку|тур|ночь|сутки|'
    r'день|машину|автомобиль|полёт|полет|вертол[её]т)|per[^\S\n]+\w+|pro[^\S\n]+\w+|每\w+)'
)
# What may follow a bare amount: the end of the phrase, a currency or a price unit.
_AMOUNT_END = rf'(?=[^\S\n]*(?:$|[^\w\s]|{_CURRENCY}|{_PER}))'
_LABELLED = tuple(
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in (
        rf'(?<!\w){_PRICE_NOUN}[^\S\n]*(?:[:=—–-][^\S\n]*)?(?:{_LINK}[^\S\n]+)*({_NUMBER}){_AMOUNT_END}',
        rf'(?<!\w){_PRICE_NOUN}[^\d\n.!?:=—–]{{1,60}}[:=—–][^\S\n]*(?:{_LINK}[^\S\n]+)*({_NUMBER})',
        rf'(?<!\w){_PRICE_VERB}[^\S\n]+(?:{_LINK}[^\S\n]+)*({_NUMBER}){_AMOUNT_END}',
        rf'(?<![\d.,])({_NUMBER})[^\S\n]*{_PER}',
    )
)
_BUDGET = re.compile(r'бюджет|budget|预算', re.IGNORECASE)


def _amount(value):
    try:
        number = Decimal(re.sub(r'[ \u00a0\u202f]', '', str(value)).replace(',', '.'))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def _currency(value):
    value = str(value or '').casefold()
    for currency, words in {
        'usd': ('usd', '$', 'доллар', 'dollar'),
        'eur': ('eur', '€', 'евро'),
        'kgs': ('kgs', 'сом'),
        'rub': ('rub', 'руб'),
        'gbp': ('gbp', '£'),
        'cny': ('cny', '¥', 'юан'),
    }.items():
        if any(value.startswith(word) for word in words):
            return currency
    return None


class PriceEvidence:
    def __init__(self):
        self.prices = set()
        self.offers = {}

    def add(self, result):
        if isinstance(result, list):
            for item in result:
                self.add(item)
        elif isinstance(result, dict):
            if 'price' in result and (amount := _amount(result['price'])) is not None:
                currency = _currency(result.get('currency'))
                self.prices.add((amount, currency))
                title = result.get('title') or result.get('name')
                if isinstance(title, str) and title.strip():
                    self.offers[(title[:160], amount, currency)] = None
            for value in result.values():
                if isinstance(value, (dict, list)):
                    self.add(value)

    def accepts(self, answer, budget=''):
        for match in _MONEY.finditer(answer):
            amount = _amount(match['amount'] or match['prefixed'])
            currency = _currency(match['currency'] or match['prefix'])
            context = re.split(r'[.!?\n]', answer[: match.start()])[-1][-80:]
            if _BUDGET.search(context) and match.group().casefold() in budget.casefold():
                continue
            if (amount, currency) not in self.prices:
                return False
        amounts = {amount for amount, _ in self.prices}
        return all(
            _amount(match[1]) in amounts
            for pattern in _LABELLED
            for match in pattern.finditer(answer)
        )

    def fallback(self, language):
        if not self.offers:
            return PRICE_UNAVAILABLE.get(language, PRICE_UNAVAILABLE['ru'])
        unknown = {
            'ru': 'валюта не указана',
            'ky': 'валюта көрсөтүлгөн эмес',
            'en': 'currency not specified',
            'de': 'Währung nicht angegeben',
            'zh': '币种未注明',
        }.get(language, 'валюта не указана')
        return '\n'.join(
            f'{title} — {amount:f} {currency.upper() if currency else unknown}.'
            for title, amount, currency in list(self.offers)[:3]
        )


PRICE_RECHECK = (
    'Цена или валюта в черновике не подтверждена настоящими Tools. '
    'Не цитируй черновик и цены из сообщения клиента. Сам вызови search_catalogue '
    'или get_catalogue_item и ответь только по их результату. '
    'Если currency=null, валюта неизвестна: не добавляй USD, доллары или другую валюту.'
)

PRICE_UNAVAILABLE = {
    'ru': 'Не удалось подтвердить цену по каталогу. Уточните название услуги.',
    'ky': 'Каталогдон бааны ырастоо мүмкүн болгон жок. Кызматтын атын тактаңыз.',
    'en': 'The price could not be verified in the catalogue. Please clarify the service name.',
    'de': 'Der Preis konnte im Katalog nicht bestätigt werden. Welche Leistung meinen Sie?',
    'zh': '无法从目录中确认价格。请说明服务名称。',
}
