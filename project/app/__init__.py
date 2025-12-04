import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static')
    )
    app.config['SECRET_KEY'] = 'dev'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        from .models import User, Role, SystemSetting
        db.create_all()
        
        # 初始化基础数据
        if not Role.query.first():
            admin_role = Role(name='admin', description='管理员')
            user_role = Role(name='user', description='普通用户')
            db.session.add_all([admin_role, user_role])
            db.session.commit()
            
            # 默认管理员 admin/123456
            admin = User(username='admin', role=admin_role)
            admin.set_password('123456')
            db.session.add(admin)
            db.session.commit()
            
        # 初始化系统设置
        if not SystemSetting.query.filter_by(key='app_name').first():
            db.session.add(SystemSetting(key='app_name', value='政企智能舆情分析报告生成智能体应用系统'))
            db.session.commit()

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)
    
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from .admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    return app

