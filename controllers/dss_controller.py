from flask import Blueprint, jsonify, render_template

dss_blueprint = Blueprint("dss", __name__)

@dss_blueprint.get("/dss")
def dss_page():

    return render_template("dss.html")

@dss_blueprint.get("/api/dss/status")
def dss_status():

    return jsonify(
{
"status": "ok",
"module": "RealtyVision DSS",
"laboratory": 1,
"stage": "Базовий каркас інтерфейсу",
"screens": [
"Експертиза",
"Модель та дані",
"Експертна логіка",
"Результати та аналіз",
],
}
)
