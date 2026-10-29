import json
import os


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
    message_limit = max(1, int(os.getenv('CHAT_HISTORY_MESSAGES', '12')))
    character_limit = max(1, int(os.getenv('CHAT_HISTORY_CHARACTERS', '8000')))
    selected = []
    characters = 0
    for item in reversed(history[-message_limit:]):
        if item.role not in ('user', 'assistant') or not isinstance(item.content, str):
            continue
        if characters + len(item.content) > character_limit:
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
