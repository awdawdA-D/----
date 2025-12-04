from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from .models import User, Role, SystemSetting, db

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('您没有权限访问该页面')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
@login_required
@admin_required
def index():
    return render_template('admin/index.html')

@bp.route('/users')
@login_required
@admin_required
def users():
    users = User.query.all()
    roles = Role.query.all()
    return render_template('admin/users.html', users=users, roles=roles)

@bp.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role_id = request.form.get('role_id')
    
    if User.query.filter_by(username=username).first():
        flash('用户名已存在')
    else:
        user = User(username=username, role_id=role_id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('用户添加成功')
    return redirect(url_for('admin.users'))

@bp.route('/users/delete/<int:id>')
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        flash('不能删除超级管理员')
    else:
        db.session.delete(user)
        db.session.commit()
        flash('用户删除成功')
    return redirect(url_for('admin.users'))

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        app_name = request.form.get('app_name')
        
        setting = SystemSetting.query.filter_by(key='app_name').first()
        if not setting:
            setting = SystemSetting(key='app_name')
            db.session.add(setting)
        
        setting.value = app_name
        db.session.commit()
        flash('设置已更新')
        
    app_name = SystemSetting.query.filter_by(key='app_name').first()
    return render_template('admin/settings.html', app_name=app_name.value if app_name else '')
