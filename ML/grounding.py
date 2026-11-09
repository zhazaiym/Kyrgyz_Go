"""Reject extracted place names the client never wrote, such as a model typo of Иссык-Куль."""

import re
from difflib import SequenceMatcher

_LATIN = dict(
    zip(
        'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
        'a b v g d e e zh z i i k l m n o p r s t u f h c ch sh sh _ y _ e yu ya'.split(),
    )
)
_LATIN.update({'ъ': '', 'ь': ''})
# Kyrgyz letters and CJK mean the client may name the place in a form we cannot compare.
_UNCOMPARABLE = re.compile(r'[өүңӨҮҢ぀-ヿ㐀-鿿]')
_THRESHOLD = 0.75


def _latin(text):
    lowered = ''.join(_LATIN.get(char, char) for char in text.lower())
    return re.sub(r'[^a-z0-9]+', ' ', lowered).split()


def grounded(value, text):
    """True when value matches up to three adjacent words of text, allowing inflection."""
    target = ''.join(_latin(value))
    words = _latin(text)
    if not target:
        return True
    for start in range(len(words)):
        for end in range(start + 1, min(start + 3, len(words)) + 1):
            window = ''.join(words[start:end])
            if SequenceMatcher(None, target, window).ratio() >= _THRESHOLD:
                return True
    return False


def destination_is_trusted(value, text, language):
    if language in ('ky', 'zh') or _UNCOMPARABLE.search(text):
        return True
    return grounded(value, text)
