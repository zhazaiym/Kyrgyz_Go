import json
from types import SimpleNamespace

from ML.config import chat_setting


def text_content(content):
    """Read only text blocks; never stringify provider metadata or tool calls."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(
            item if isinstance(item, str) else item.get('text', '')
            for item in content
            if isinstance(item, str)
            or (isinstance(item, dict) and isinstance(item.get('text'), str))
        )
    return ''


def recent_messages(history):
    message_limit = chat_setting('CHAT_HISTORY_MESSAGES')
    character_limit = chat_setting('CHAT_HISTORY_CHARACTERS')
    selected = []
    characters = 0
    for item in reversed(history[-message_limit:]):
        if item.role not in ('user', 'assistant') or not isinstance(item.content, str):
            continue
        remaining = character_limit - characters
        if remaining <= 0:
            break
        if len(item.content) > remaining:
            selected.append(SimpleNamespace(role=item.role, content=item.content[-remaining:]))
            break
        selected.append(item)
        characters += len(item.content)
    return list(reversed(selected))


def extraction_context(history):
    remaining = 2400
    selected = []
    for item in reversed(history[-4:]):
        if item.role not in ('user', 'assistant') or not isinstance(item.content, str):
            continue
        content = item.content[-remaining:]
        selected.append({'role': item.role, 'content': content})
        remaining -= len(content)
        if remaining <= 0:
            break
    return json.dumps(list(reversed(selected)), ensure_ascii=False)
