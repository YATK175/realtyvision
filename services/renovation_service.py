import json
import logging
from pathlib import Path
from config import PROMPTS_FOLDER

logger = logging.getLogger(__name__)

_REALTY_TYPE_UA = {'apartment': 'квартира', 'house': 'будинок'}


def generate_renovation_plan(data: dict) -> dict:
    try:
        return _generate_with_llm(data)
    except Exception as exc:
        logger.warning('Renovation LLM failed: %s', exc)
        return _generate_fallback(data)


def _generate_with_llm(data: dict) -> dict:
    from services.groq_client import chat_text_only as groq_text, GroqUnavailable
    from services.openrouter_client import chat_text_only as or_text, OpenRouterUnavailable

    prompt_path = PROMPTS_FOLDER / 'renovation_advisor.txt'
    template = prompt_path.read_text(encoding='utf-8')
    prompt = template.format(**_build_vars(data))

    raw = None
    try:
        raw = groq_text(prompt)
    except GroqUnavailable:
        raw = or_text(prompt)

    start = raw.find('{')
    end = raw.rfind('}') + 1
    if start == -1 or end == 0:
        raise ValueError('No JSON in LLM response')
    return json.loads(raw[start:end])


def _build_vars(data: dict) -> dict:
    defects = data.get('defects', [])
    features = data.get('features', [])
    return {
        'realty_type_ua': _REALTY_TYPE_UA.get(data.get('realty_type', 'apartment'), 'квартира'),
        'city_name': data.get('city_name', 'невідоме місто'),
        'rooms_count': data.get('rooms_count', 1),
        'final_area': data.get('final_area', 50),
        'condition_score': data.get('condition_score', 3),
        'condition_label': data.get('condition_label', 'Середній'),
        'defects': ', '.join(defects) if defects else 'не виявлено',
        'features': ', '.join(features) if features else 'не виявлено',
        'base_price_per_m2': data.get('base_price_per_m2', 800),
        'final_price': data.get('final_price', 40000),
    }


def _generate_fallback(data: dict) -> dict:
    score = data.get('condition_score', 3)
    area = data.get('final_area', 50)
    price = data.get('final_price', 40000)

    base_cost_per_m2 = {1: 350, 2: 200, 3: 100, 4: 40, 5: 0}.get(score, 100)
    total_min = round(area * base_cost_per_m2 * 0.7)
    total_max = round(area * base_cost_per_m2 * 1.3)
    potential_pct = {1: 30, 2: 20, 3: 12, 4: 5, 5: 2}.get(score, 10)

    items = []
    if score <= 2:
        items.extend([
            {
                'name': 'Комплексний косметичний ремонт',
                'priority': 'high',
                'cost_min': round(area * 80),
                'cost_max': round(area * 150),
                'value_gain': round(price * 0.12),
                'description': 'Фарбування стін, заміна підлоги, оновлення сантехніки',
            },
            {
                'name': 'Заміна вікон',
                'priority': 'high',
                'cost_min': 300 * data.get('rooms_count', 2),
                'cost_max': 600 * data.get('rooms_count', 2),
                'value_gain': round(price * 0.05),
                'description': 'Металопластикові вікна з енергозбереженням',
            },
        ])
    if score <= 3:
        items.extend([
            {
                'name': 'Оновлення кухні',
                'priority': 'medium',
                'cost_min': 800,
                'cost_max': 2500,
                'value_gain': round(price * 0.04),
                'description': 'Нові фасади кухонного гарнітуру, стільниця, фартух',
            },
            {
                'name': 'Ремонт ванної кімнати',
                'priority': 'medium',
                'cost_min': 600,
                'cost_max': 2000,
                'value_gain': round(price * 0.03),
                'description': 'Нова плитка, сантехніка, вентиляція',
            },
        ])
    items.append({
        'name': 'Оновлення освітлення',
        'priority': 'low',
        'cost_min': 150,
        'cost_max': 400,
        'value_gain': round(price * 0.01),
        'description': 'LED-освітлення у всіх кімнатах, точкові світильники',
    })

    return {
        'potential_value_increase_pct': potential_pct,
        'total_cost_min': total_min,
        'total_cost_max': total_max,
        'items': items,
    }
