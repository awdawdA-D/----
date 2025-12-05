from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from . import db

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    description = db.Column(db.String(255))
    
    # 预定义角色: 'admin', 'user'
    
    def __repr__(self):
        return f'<Role {self.name}>'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    role = db.relationship('Role', backref='users')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    @property
    def is_admin(self):
        return self.role and self.role.name == 'admin'

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)

class CollectionRecord(db.Model):
    __tablename__ = 'collection_records'
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(128))
    title = db.Column(db.String(512))
    summary = db.Column(db.Text)
    source = db.Column(db.String(128))
    original_url = db.Column(db.String(1024))
    cover = db.Column(db.String(1024))
    deep_collected = db.Column(db.Boolean, default=False)
    deep_content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CollectionRule(db.Model):
    __tablename__ = 'collection_rules'
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(255))
    site = db.Column(db.String(255), unique=True, nullable=False)
    title_xpath = db.Column(db.String(1024))
    content_xpath = db.Column(db.String(2048))
    headers_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AiEngine(db.Model):
    __tablename__ = 'ai_engines'
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(128))
    api_base = db.Column(db.Text)
    api_key = db.Column(db.Text)
    model_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
