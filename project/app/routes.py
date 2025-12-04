from flask import Blueprint, render_template
from flask_login import login_required, current_user
from .models import SystemSetting

bp = Blueprint('main', __name__)

@bp.context_processor
def inject_settings():
    app_name_setting = SystemSetting.query.filter_by(key='app_name').first()
    return dict(site_name=app_name_setting.value if app_name_setting else '舆情系统')

@bp.route('/')
@login_required
def index():
    return render_template('index.html')

@bp.route('/daily')
@login_required
def daily():
    return render_template('daily.html')
