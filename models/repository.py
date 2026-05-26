import json
from datetime import datetime
from models.database import get_connection


# ──────────────────────────────────────────────────────────────────────────────
# Evaluations
# ──────────────────────────────────────────────────────────────────────────────

def save_evaluation(
    browser_id: str,
    evaluation: dict,
    input_data: dict,
    photo_ids: list,
    user_id: int | None = None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO evaluations (
                created_at, browser_id, user_id,
                state_id, state_name, city_id, city_name,
                realty_type, rooms_count, floor, total_floors, year_built,
                user_area, user_description,
                final_area, area_source,
                condition_score, condition_label,
                base_price_per_m2, price_source,
                final_price, price_min, price_max,
                coefficients_json, factors_json, explanation, mode
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                browser_id,
                user_id,
                input_data.get('state_id'),
                input_data.get('state_name', ''),
                input_data.get('city_id'),
                input_data.get('city_name', ''),
                input_data.get('realty_type'),
                input_data.get('rooms_count'),
                input_data.get('floor'),
                input_data.get('total_floors'),
                input_data.get('year_built'),
                input_data.get('user_area'),
                input_data.get('user_description', ''),
                evaluation['final_area'],
                evaluation['area_source'],
                evaluation['condition_score'],
                evaluation['condition_label'],
                evaluation['base_price_per_m2'],
                evaluation['price_source'],
                evaluation['final_price'],
                evaluation['price_min'],
                evaluation['price_max'],
                json.dumps(evaluation.get('coefficients', {}), ensure_ascii=False),
                json.dumps(evaluation.get('factors', []), ensure_ascii=False),
                evaluation.get('explanation', ''),
                evaluation.get('mode', 'full'),
            ),
        )
        eval_id = cur.lastrowid

        for idx, filename in enumerate(photo_ids):
            conn.execute(
                'INSERT INTO evaluation_photos (evaluation_id, filename, order_index) VALUES (?, ?, ?)',
                (eval_id, filename, idx),
            )

        # Record price to history for analytics
        _record_price_history(
            conn,
            state_id=input_data.get('state_id'),
            city_id=input_data.get('city_id'),
            state_name=input_data.get('state_name', ''),
            city_name=input_data.get('city_name', ''),
            realty_type=input_data.get('realty_type'),
            rooms_count=input_data.get('rooms_count'),
            price_per_m2=evaluation['base_price_per_m2'],
        )

        conn.commit()
        return eval_id
    finally:
        conn.close()


def _record_price_history(
    conn, state_id, city_id, state_name, city_name, realty_type, rooms_count, price_per_m2
):
    if not all([state_id, city_id, realty_type, rooms_count, price_per_m2]):
        return
    now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    conn.execute(
        """
        INSERT INTO price_history
            (state_id, city_id, state_name, city_name, realty_type, rooms_count, price_per_m2, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (state_id, city_id, state_name, city_name, realty_type, rooms_count, price_per_m2, now),
    )


def get_history(
    browser_id: str,
    user_id: int | None = None,
    realty_type: str = '',
    state_id: int | None = None,
    city_id: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    date_from: str = '',
    date_to: str = '',
    condition_min: int | None = None,
    sort: str = 'date_desc',
    page: int = 1,
    per_page: int = 20,
) -> dict:
    conn = get_connection()
    try:
        where = []
        params = []

        if user_id:
            where.append('e.user_id = ?')
            params.append(user_id)
        else:
            where.append('e.browser_id = ?')
            params.append(browser_id)

        if realty_type:
            where.append('e.realty_type = ?')
            params.append(realty_type)
        if state_id:
            where.append('e.state_id = ?')
            params.append(state_id)
        if city_id:
            where.append('e.city_id = ?')
            params.append(city_id)
        if price_min is not None:
            where.append('e.final_price >= ?')
            params.append(price_min)
        if price_max is not None:
            where.append('e.final_price <= ?')
            params.append(price_max)
        if date_from:
            where.append('e.created_at >= ?')
            params.append(date_from)
        if date_to:
            where.append('e.created_at <= ?')
            params.append(date_to + 'T23:59:59')
        if condition_min is not None:
            where.append('e.condition_score >= ?')
            params.append(condition_min)

        where_sql = 'WHERE ' + ' AND '.join(where) if where else ''

        sort_map = {
            'date_desc': 'e.created_at DESC',
            'date_asc': 'e.created_at ASC',
            'price_desc': 'e.final_price DESC',
            'price_asc': 'e.final_price ASC',
            'condition_desc': 'e.condition_score DESC',
        }
        order_sql = sort_map.get(sort, 'e.created_at DESC')

        total = conn.execute(
            f'SELECT COUNT(*) FROM evaluations e {where_sql}', params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""
            SELECT e.id, e.created_at, e.city_name, e.state_name,
                   e.realty_type, e.rooms_count, e.final_price, e.condition_label,
                   e.condition_score, e.final_area,
                   (SELECT filename FROM evaluation_photos
                    WHERE evaluation_id = e.id ORDER BY order_index LIMIT 1) AS thumbnail
            FROM evaluations e
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            if item['thumbnail']:
                item['thumbnail'] = f"/uploads/{item['thumbnail']}"
            items.append(item)

        return {'items': items, 'total': total, 'page': page, 'per_page': per_page}
    finally:
        conn.close()


def get_evaluation(eval_id: int, browser_id: str, user_id: int | None = None) -> dict | None:
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM evaluations WHERE id = ? AND user_id = ?',
                (eval_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM evaluations WHERE id = ? AND browser_id = ?',
                (eval_id, browser_id),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data['coefficients'] = json.loads(data.pop('coefficients_json', '{}'))
        data['factors'] = json.loads(data.pop('factors_json', '[]'))
        if data.get('renovation_json'):
            data['renovation_plan'] = json.loads(data.pop('renovation_json'))
        else:
            data.pop('renovation_json', None)
            data['renovation_plan'] = None
        photos = conn.execute(
            'SELECT filename, order_index, detected_room FROM evaluation_photos WHERE evaluation_id = ? ORDER BY order_index',
            (eval_id,),
        ).fetchall()
        data['photos'] = [dict(p) for p in photos]
        return data
    finally:
        conn.close()


def delete_evaluation(eval_id: int, browser_id: str, user_id: int | None = None) -> list[str] | None:
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT id FROM evaluations WHERE id = ? AND user_id = ?', (eval_id, user_id)
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT id FROM evaluations WHERE id = ? AND browser_id = ?', (eval_id, browser_id)
            ).fetchone()
        if row is None:
            return None
        filenames = [
            r['filename']
            for r in conn.execute(
                'SELECT filename FROM evaluation_photos WHERE evaluation_id = ?', (eval_id,)
            ).fetchall()
        ]
        conn.execute('DELETE FROM evaluations WHERE id = ?', (eval_id,))
        conn.commit()
        return filenames
    finally:
        conn.close()


def get_compare(ids: list[int], browser_id: str, user_id: int | None = None) -> list[dict]:
    result = []
    for eval_id in ids[:4]:
        data = get_evaluation(eval_id, browser_id, user_id)
        if data:
            for photo in data.get('photos', []):
                photo['url'] = f"/uploads/{photo['filename']}"
            result.append(data)
    return result


def save_renovation_plan(eval_id: int, plan: dict, browser_id: str, user_id: int | None = None):
    conn = get_connection()
    try:
        if user_id:
            conn.execute(
                'UPDATE evaluations SET renovation_json = ? WHERE id = ? AND user_id = ?',
                (json.dumps(plan, ensure_ascii=False), eval_id, user_id),
            )
        else:
            conn.execute(
                'UPDATE evaluations SET renovation_json = ? WHERE id = ? AND browser_id = ?',
                (json.dumps(plan, ensure_ascii=False), eval_id, browser_id),
            )
        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Price analytics
# ──────────────────────────────────────────────────────────────────────────────

def get_price_analytics(
    state_id: int,
    city_id: int | None = None,
    realty_type: str = 'apartment',
    rooms_count: int = 2,
) -> list[dict]:
    conn = get_connection()
    try:
        where = ['state_id = ?', 'realty_type = ?', 'rooms_count = ?']
        params = [state_id, realty_type, rooms_count]
        if city_id:
            where.append('city_id = ?')
            params.append(city_id)

        rows = conn.execute(
            f"""
            SELECT DATE(recorded_at) AS day, AVG(price_per_m2) AS avg_price,
                   COUNT(*) AS cnt, city_name
            FROM price_history
            WHERE {' AND '.join(where)}
            GROUP BY DATE(recorded_at), city_id
            ORDER BY day ASC
            LIMIT 90
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_analytics_summary(browser_id: str = '', user_id: int | None = None) -> dict:
    conn = get_connection()
    try:
        if user_id:
            owner_clause = 'WHERE user_id = ?'
            owner_params = [user_id]
        else:
            owner_clause = 'WHERE browser_id = ?'
            owner_params = [browser_id]

        total_evals = conn.execute(
            f'SELECT COUNT(*) FROM evaluations {owner_clause}', owner_params
        ).fetchone()[0]

        top_cities = conn.execute(
            f"""
            SELECT city_name, state_name, COUNT(*) as cnt, AVG(final_price) as avg_price
            FROM evaluations
            {owner_clause}
            GROUP BY city_id
            ORDER BY cnt DESC
            LIMIT 5
            """,
            owner_params,
        ).fetchall()

        avg_price = conn.execute(
            f'SELECT AVG(final_price) FROM evaluations {owner_clause}', owner_params
        ).fetchone()[0]

        return {
            'total_evaluations': total_evals,
            'avg_price': round(avg_price or 0),
            'top_cities': [dict(r) for r in top_cities],
        }
    finally:
        conn.close()
