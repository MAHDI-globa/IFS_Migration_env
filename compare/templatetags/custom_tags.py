import json
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, '')

@register.filter
def get_index(sequence, i):
    try:
        return sequence[i]
    except (IndexError, TypeError):
        return []

@register.filter
def tojson(value):
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return '{}'
