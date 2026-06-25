import json
import logging
import uuid
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, session, render_template_string
from controllers.dss_controller import dss_blueprint

import config
from models.database import init_db
from controllers.dss_expert_controller import dss_expert_blueprint
from models.dss_expert_database import init_dss_expert_database
from models.dss_database import init_dss_database
from controllers.dss_controller import dss_blueprint
from models import repository

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

init_dss_database()
init_dss_expert_database()
app.register_blueprint(dss_blueprint)
app.register_blueprint(dss_expert_blueprint)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024 * config.MAX_PHOTOS
app.secret_key = config.SECRET_KEY

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _current_user() -> dict | None:
    uid = session.get('user_id')
    if not uid:
        return None
    from services.auth_service import get_user
    return get_user(uid)


# ──────────────────────────────────────────────────────────────────────────────
# Static pages
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(str(config.BASE_DIR / 'templates'), 'index.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(str(config.UPLOAD_FOLDER), filename)


@app.route('/print/<int:eval_id>')
def print_evaluation(eval_id):
    user = _current_user()
    user_id = user['id'] if user else None
    browser_id = request.args.get('browser_id', '')
    data = repository.get_evaluation(eval_id, browser_id, user_id)
    if data is None:
        return 'Оцінку не знайдено', 404
    for photo in data.get('photos', []):
        photo['url'] = f"/uploads/{photo['filename']}"
    return _render_print_page(data)


# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    body = request.get_json(silent=True) or {}
    try:
        from services.auth_service import register
        user = register(
            email=body.get('email', ''),
            name=body.get('name', ''),
            password=body.get('password', ''),
        )
        session['user_id'] = user['id']
        return jsonify({'user': user})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.exception('register: %s', exc)
        return jsonify({'error': 'Внутрішня помилка'}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    body = request.get_json(silent=True) or {}
    from services.auth_service import login
    user = login(email=body.get('email', ''), password=body.get('password', ''))
    if user is None:
        return jsonify({'error': 'Невірний email або пароль'}), 401
    session['user_id'] = user['id']
    return jsonify({'user': user})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.pop('user_id', None)
    return jsonify({'status': 'ok'})


@app.route('/api/auth/me')
def auth_me():
    user = _current_user()
    if not user:
        return jsonify({'user': None})
    return jsonify({'user': user})


# ──────────────────────────────────────────────────────────────────────────────
# System
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/health')
def health():
    from services.provider_registry import get_status
    return jsonify(get_status())


@app.route('/api/regions')
def get_regions():
    if not config.REGIONS_FILE.exists():
        from models.database import _ensure_regions
        _ensure_regions()
    if not config.REGIONS_FILE.exists():
        return jsonify([])
    try:
        data = json.loads(config.REGIONS_FILE.read_text(encoding='utf-8'))
        return jsonify([{'state_id': r['state_id'], 'name': r['name']} for r in data])
    except Exception as exc:
        logger.error('get_regions: %s', exc)
        return jsonify({'error': 'Не вдалося завантажити регіони'}), 500


@app.route('/api/cities/<int:state_id>')
def get_cities(state_id):
    if not config.REGIONS_FILE.exists():
        return jsonify([])
    try:
        data = json.loads(config.REGIONS_FILE.read_text(encoding='utf-8'))
        for region in data:
            if region['state_id'] == state_id:
                return jsonify(region.get('cities', []))
        return jsonify([])
    except Exception as exc:
        logger.error('get_cities(%d): %s', state_id, exc)
        return jsonify({'error': 'Помилка завантаження міст'}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Evaluate
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    errors = _validate_evaluate_request(request)
    if errors:
        return jsonify({'error': '; '.join(errors)}), 400

    photos = request.files.getlist('photos[]')
    if not photos or all(f.filename == '' for f in photos):
        return jsonify({'error': 'Необхідно завантажити хоча б одне фото'}), 400
    if len(photos) > config.MAX_PHOTOS:
        return jsonify({'error': f'Максимум {config.MAX_PHOTOS} фото'}), 400

    state_id = int(request.form['state_id'])
    city_id = int(request.form['city_id'])
    realty_type = request.form['realty_type']
    rooms_count = int(request.form['rooms_count'])
    floor = _int_or_none(request.form.get('floor'))
    total_floors = _int_or_none(request.form.get('total_floors'))
    year_built = _int_or_none(request.form.get('year_built'))
    user_area = _float_or_none(request.form.get('user_area'))
    user_description = request.form.get('user_description', '').strip()

    saved_paths = []
    photo_ids = []
    try:
        for photo in photos:
            if photo.filename == '':
                continue
            if not _allowed(photo.filename):
                return jsonify({'error': f'Непідтримуваний формат: {photo.filename}'}), 400
            uid = uuid.uuid4().hex + '.jpg'
            raw_path = config.UPLOAD_FOLDER / ('_raw_' + uid)
            final_path = config.UPLOAD_FOLDER / uid
            photo.save(str(raw_path))
            saved_paths.append(raw_path)
            photo_ids.append(uid)

            from services.vision_service import prepare_image
            prepare_image(raw_path, final_path)
            raw_path.unlink(missing_ok=True)

        final_paths = [config.UPLOAD_FOLDER / pid for pid in photo_ids]

        from services.vision_service import analyze_photos
        vision = analyze_photos(final_paths, user_description=user_description or None)

        if user_area and user_area > 0:
            final_area = user_area
            area_source = 'user'
        elif vision.get('estimated_area_midpoint'):
            final_area = round(vision['estimated_area_midpoint'], 1)
            area_source = 'estimated'
        else:
            final_area = _default_area(realty_type, rooms_count)
            area_source = 'estimated'

        from services.price_service import get_base_price
        price_info = get_base_price(state_id, city_id, realty_type, rooms_count)

        from services.rules_engine import calculate_price
        price_result = calculate_price(
            base_price_per_m2=price_info['price_per_m2'],
            area=final_area,
            condition_score=vision['condition_score'],
            floor=floor,
            total_floors=total_floors,
            year_built=year_built,
            realty_type=realty_type,
            area_source=area_source,
        )

        state_name, city_name = _resolve_names(state_id, city_id)

        from services.provider_registry import decide_mode
        mode = decide_mode()
        use_llm = mode in ('full', 'full_with_cached_prices')

        explanation_data = {
            'city_name': city_name,
            'state_name': state_name,
            'realty_type': realty_type,
            'rooms_count': rooms_count,
            'final_area': final_area,
            'area_source': area_source,
            'floor': floor,
            'total_floors': total_floors,
            'year_built': year_built,
            'condition_score': vision['condition_score'],
            'condition_label': vision['condition_label'],
            'defects': vision.get('defects', []),
            'features': vision.get('features', []),
            'base_price_per_m2': price_info['price_per_m2'],
            'price_source': price_info['source'],
            'user_description': user_description,
            'coefficients': price_result['coefficients'],
            **price_result,
        }

        from services.explanation_service import generate
        explanation = generate(explanation_data, use_llm=use_llm)

        factors = []
        for d in vision.get('defects', []):
            factors.append({'type': 'negative', 'text': d})
        for f in vision.get('features', []):
            factors.append({'type': 'positive', 'text': f})

        evaluation = {
            'final_price': price_result['final_price'],
            'price_min': price_result['price_min'],
            'price_max': price_result['price_max'],
            'currency': 'USD',
            'final_area': final_area,
            'area_source': area_source,
            'condition_score': vision['condition_score'],
            'condition_label': vision['condition_label'],
            'base_price_per_m2': price_info['price_per_m2'],
            'price_source': price_info['source'],
            'price_sample_size': price_info.get('sample_size', 0),
            'coefficients': price_result['coefficients'],
            'factors': factors,
            'defects': vision.get('defects', []),
            'features': vision.get('features', []),
            'explanation': explanation,
            'mode': mode,
            'photos_analyzed': len(final_paths),
            'state_id': state_id,
            'state_name': state_name,
            'city_id': city_id,
            'city_name': city_name,
            'realty_type': realty_type,
            'rooms_count': rooms_count,
            'floor': floor,
            'total_floors': total_floors,
            'year_built': year_built,
            'user_area': user_area,
            'user_description': user_description,
        }

        return jsonify({'evaluation': evaluation, 'photo_ids': photo_ids})

    except Exception as exc:
        logger.exception('evaluate: %s', exc)
        for p in saved_paths:
            p.unlink(missing_ok=True)
        return jsonify({'error': f'Внутрішня помилка: {exc}'}), 500


@app.route('/api/save', methods=['POST'])
def save_evaluation():
    body = request.get_json(silent=True) or {}
    browser_id = body.get('browser_id', '').strip()
    evaluation = body.get('evaluation')
    input_data = body.get('input', {})
    photo_ids = body.get('photo_ids', [])

    if not evaluation:
        return jsonify({'error': 'Відсутній evaluation'}), 400

    user = _current_user()
    user_id = user['id'] if user else None

    if not browser_id and not user_id:
        return jsonify({'error': 'Відсутній browser_id або сесія'}), 400

    input_merged = {
        'state_id': evaluation.get('state_id'),
        'state_name': evaluation.get('state_name', ''),
        'city_id': evaluation.get('city_id'),
        'city_name': evaluation.get('city_name', ''),
        'realty_type': evaluation.get('realty_type'),
        'rooms_count': evaluation.get('rooms_count'),
        'floor': evaluation.get('floor'),
        'total_floors': evaluation.get('total_floors'),
        'year_built': evaluation.get('year_built'),
        'user_area': evaluation.get('user_area'),
        'user_description': evaluation.get('user_description', ''),
        **input_data,
    }

    try:
        eval_id = repository.save_evaluation(
            browser_id, evaluation, input_merged, photo_ids, user_id=user_id
        )
        return jsonify({'id': eval_id, 'status': 'saved'})
    except Exception as exc:
        logger.exception('save_evaluation: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# History
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/history')
def get_history():
    user = _current_user()
    user_id = user['id'] if user else None
    browser_id = request.args.get('browser_id', '').strip()

    if not browser_id and not user_id:
        return jsonify({'error': 'Потрібна авторизація або browser_id'}), 400

    result = repository.get_history(
        browser_id=browser_id,
        user_id=user_id,
        realty_type=request.args.get('realty_type', ''),
        state_id=_int_or_none(request.args.get('state_id')),
        city_id=_int_or_none(request.args.get('city_id')),
        price_min=_float_or_none(request.args.get('price_min')),
        price_max=_float_or_none(request.args.get('price_max')),
        date_from=request.args.get('date_from', ''),
        date_to=request.args.get('date_to', ''),
        condition_min=_int_or_none(request.args.get('condition_min')),
        sort=request.args.get('sort', 'date_desc'),
        page=max(1, int(request.args.get('page', 1))),
        per_page=min(100, int(request.args.get('per_page', 20))),
    )
    return jsonify(result)


@app.route('/api/history/<int:eval_id>', methods=['GET', 'DELETE'])
def history_item(eval_id):
    user = _current_user()
    user_id = user['id'] if user else None
    browser_id = request.args.get('browser_id', '').strip()

    if request.method == 'DELETE':
        filenames = repository.delete_evaluation(eval_id, browser_id, user_id)
        if filenames is None:
            return jsonify({'error': 'Запис не знайдено'}), 404
        for fname in filenames:
            (config.UPLOAD_FOLDER / fname).unlink(missing_ok=True)
        return jsonify({'status': 'deleted'})

    data = repository.get_evaluation(eval_id, browser_id, user_id)
    if data is None:
        return jsonify({'error': 'Запис не знайдено'}), 404
    for photo in data.get('photos', []):
        photo['url'] = f"/uploads/{photo['filename']}"
    return jsonify(data)


# ──────────────────────────────────────────────────────────────────────────────
# Compare
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/compare')
def compare():
    ids_param = request.args.get('ids', '')
    if not ids_param:
        return jsonify({'error': 'Параметр ids обов\'язковий'}), 400

    ids = []
    for part in ids_param.split(','):
        try:
            ids.append(int(part.strip()))
        except ValueError:
            pass
    if len(ids) < 2:
        return jsonify({'error': 'Потрібно мінімум 2 ідентифікатора'}), 400

    user = _current_user()
    user_id = user['id'] if user else None
    browser_id = request.args.get('browser_id', '').strip()

    items = repository.get_compare(ids, browser_id, user_id)
    return jsonify({'items': items})


# ──────────────────────────────────────────────────────────────────────────────
# Renovation advisor
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/renovations', methods=['POST'])
def get_renovation_plan():
    body = request.get_json(silent=True) or {}
    eval_id = body.get('eval_id')
    user = _current_user()
    user_id = user['id'] if user else None
    browser_id = body.get('browser_id', '')

    eval_data = None
    if eval_id:
        eval_data = repository.get_evaluation(eval_id, browser_id, user_id)
        if eval_data and eval_data.get('renovation_plan'):
            return jsonify({'plan': eval_data['renovation_plan'], 'cached': True})

    if eval_data is None:
        eval_data = body.get('evaluation', {})
        if not eval_data:
            return jsonify({'error': 'Потрібен eval_id або evaluation'}), 400

    try:
        from services.renovation_service import generate_renovation_plan
        plan = generate_renovation_plan(eval_data)
        if eval_id:
            repository.save_renovation_plan(eval_id, plan, browser_id, user_id)
        return jsonify({'plan': plan, 'cached': False})
    except Exception as exc:
        logger.exception('renovation: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/api/analytics/prices')
def analytics_prices():
    state_id = _int_or_none(request.args.get('state_id'))
    if not state_id:
        return jsonify({'error': 'state_id обов\'язковий'}), 400
    data = repository.get_price_analytics(
        state_id=state_id,
        city_id=_int_or_none(request.args.get('city_id')),
        realty_type=request.args.get('realty_type', 'apartment'),
        rooms_count=int(request.args.get('rooms_count', 2)),
    )
    return jsonify({'data': data})


@app.route('/api/analytics/summary')
def analytics_summary():
    user = _current_user()
    user_id = user['id'] if user else None
    browser_id = request.args.get('browser_id', '').strip()
    return jsonify(repository.get_analytics_summary(browser_id=browser_id, user_id=user_id))


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _validate_evaluate_request(req) -> list:
    errors = []
    for field in ('state_id', 'city_id', 'realty_type', 'rooms_count'):
        if not req.form.get(field):
            errors.append(f'Поле {field} обовʼязкове')
    rt = req.form.get('realty_type')
    if rt and rt not in ('apartment', 'house'):
        errors.append('realty_type має бути apartment або house')
    rc = req.form.get('rooms_count')
    if rc:
        try:
            v = int(rc)
            if not 1 <= v <= 10:
                errors.append('rooms_count має бути від 1 до 10')
        except ValueError:
            errors.append('rooms_count має бути цілим числом')
    return errors


def _int_or_none(val) -> int | None:
    try:
        return int(val) if val else None
    except (TypeError, ValueError):
        return None


def _float_or_none(val) -> float | None:
    try:
        return float(val) if val else None
    except (TypeError, ValueError):
        return None


def _default_area(realty_type: str, rooms_count: int) -> float:
    base = {'apartment': 40, 'house': 80}.get(realty_type, 50)
    return base + rooms_count * 12


def _resolve_names(state_id: int, city_id: int) -> tuple[str, str]:
    if not config.REGIONS_FILE.exists():
        return '', ''
    try:
        regions = json.loads(config.REGIONS_FILE.read_text(encoding='utf-8'))
        state_name = ''
        city_name = ''
        for region in regions:
            if region['state_id'] == state_id:
                state_name = region['name']
                for city in region.get('cities', []):
                    if city['city_id'] == city_id:
                        city_name = city['name']
                        break
                break
        return state_name, city_name
    except Exception:
        return '', ''


def _render_print_page(data: dict) -> str:
    rt_ua = 'Квартира' if data.get('realty_type') == 'apartment' else 'Будинок'
    coef = data.get('coefficients', {})
    factors = data.get('factors', [])

    photos_html = ''
    for p in data.get('photos', [])[:6]:
        photos_html += f'<img src="{p["url"]}" class="photo">'

    factors_html = ''
    for f in factors:
        sign = '+' if f['type'] == 'positive' else '−'
        cls = f['type']
        factors_html += f'<div class="factor {cls}"><span class="sign">{sign}</span>{f["text"]}</div>'

    details = [
        ('Тип', rt_ua),
        ('Місто', f"{data.get('city_name', '')} ({data.get('state_name', '')})"),
        ('Кімнат', str(data.get('rooms_count', ''))),
        ('Площа', f"{data.get('final_area', '')} м²"),
        ('Стан', f"{data.get('condition_score', '')}/5 — {data.get('condition_label', '')}"),
        ('Базова ціна/м²', f"${data.get('base_price_per_m2', 0):,.0f}"),
    ]
    if data.get('floor') and data.get('total_floors'):
        details.append(('Поверх', f"{data['floor']} з {data['total_floors']}"))
    if data.get('year_built'):
        details.append(('Рік побудови', str(data['year_built'])))

    details_html = ''.join(f'<tr><td class="label">{k}</td><td>{v}</td></tr>' for k, v in details)

    coef_html = ''
    for name, key in [('Стан', 'condition'), ('Поверх', 'floor'), ('Рік', 'year'), ('Загальний', 'combined')]:
        val = coef.get(key, 1.0)
        cls = 'pos' if val > 1.01 else ('neg' if val < 0.99 else '')
        coef_html += f'<tr><td>{name}</td><td class="coef {cls}">×{val}</td></tr>'

    explanation = (data.get('explanation') or '').replace('\n', '<br>')
    date_str = (data.get('created_at', '') or '')[:10]
    title = f"{rt_ua}: {data.get('city_name', '')}, {data.get('rooms_count', '')}-кімн."

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<title>RealtyVision — {title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; font-size: 13px; color: #111; background: #fff; padding: 32px 40px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #ff4500; padding-bottom: 12px; margin-bottom: 24px; }}
  .brand {{ font-size: 20px; font-weight: 900; color: #ff4500; letter-spacing: -0.5px; }}
  .date {{ color: #666; font-size: 12px; }}
  h1 {{ font-size: 16px; font-weight: 700; margin-bottom: 4px; }}
  .price-block {{ text-align: center; border: 2px solid #ff4500; border-radius: 4px; padding: 20px; margin: 20px 0; background: #fff8f5; }}
  .price-main {{ font-size: 42px; font-weight: 900; color: #ff4500; letter-spacing: -2px; }}
  .price-range {{ font-size: 13px; color: #666; margin-top: 4px; }}
  .section {{ margin: 20px 0; }}
  .section-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #999; margin-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #eee; }}
  .label {{ color: #666; width: 140px; }}
  .coef {{ font-weight: 700; }}
  .coef.pos {{ color: #16a34a; }}
  .coef.neg {{ color: #dc2626; }}
  .factor {{ display: flex; gap: 8px; padding: 3px 0; font-size: 12px; border-bottom: 1px solid #f0f0f0; }}
  .factor.positive .sign {{ color: #16a34a; font-weight: 900; }}
  .factor.negative .sign {{ color: #dc2626; font-weight: 900; }}
  .photos {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .photo {{ width: 140px; height: 105px; object-fit: cover; border-radius: 3px; border: 1px solid #ddd; }}
  .explanation {{ font-size: 12px; line-height: 1.7; color: #333; white-space: pre-line; }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 11px; color: #999; text-align: center; }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="brand">RealtyVision</div>
    <h1>{title}</h1>
  </div>
  <div class="date">{date_str}</div>
</div>

<div class="price-block">
  <div style="font-size:11px;font-weight:700;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Орієнтовна вартість</div>
  <div class="price-main">${data.get('final_price', 0):,.0f}</div>
  <div class="price-range">Діапазон: ${data.get('price_min', 0):,.0f} — ${data.get('price_max', 0):,.0f}</div>
</div>

{"<div class='section'><div class='section-title'>Фото</div><div class='photos'>" + photos_html + "</div></div>" if photos_html else ""}

<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
  <div class="section">
    <div class="section-title">Параметри об'єкта</div>
    <table>{details_html}</table>
  </div>
  <div class="section">
    <div class="section-title">Коригувальні коефіцієнти</div>
    <table>{coef_html}</table>
  </div>
</div>

{"<div class='section'><div class='section-title'>Помічено на фото</div>" + factors_html + "</div>" if factors_html else ""}

{"<div class='section'><div class='section-title'>Пояснення</div><div class='explanation'>" + explanation + "</div></div>" if explanation else ""}

<div class="footer">
  Це не офіційна експертна оцінка. Для угод з нерухомістю звертайтеся до сертифікованого оцінювача.
</div>

<script>window.onload = function() {{ window.print(); }}</script>
</body>
</html>"""


if __name__ == '__main__':
    config.UPLOAD_FOLDER.mkdir(exist_ok=True)
    config.DATA_FOLDER.mkdir(exist_ok=True)
    init_db()
    app.run(host='127.0.0.1', port=config.PORT, debug=False)
