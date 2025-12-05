from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from functools import wraps
from .models import User, Role, SystemSetting, db, CollectionRecord, CollectionRule, AiEngine, CrawlerSource, AiAnalysisResult
from .crawler import BaiduCrawler, XinhuaCrawler, create_crawler
import re, json
from urllib.parse import urlparse

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('您没有权限访问该页面')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@bp.after_request
def _admin_no_cache(resp):
    try:
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    except Exception:
        pass
    return resp

def fix_mojibake(s):
    if not s:
        return ''
    bad = s.count('Ã') + s.count('Â') + s.count('�')
    if bad >= 2:
        try:
            s2 = s.encode('latin-1', 'ignore').decode('utf-8', 'ignore')
            improved = sum(1 for ch in s2 if '\u4e00' <= ch <= '\u9fff')
            orig = sum(1 for ch in s if '\u4e00' <= ch <= '\u9fff')
            if improved >= orig:
                return s2
        except Exception:
            pass
    return s

@bp.route('/')
@login_required
@admin_required
def index():
    return render_template('admin/index.html')

def normalize_headers_text(s):
    if not s:
        return ''
    try:
        import re, json
        t = s
        t = t.replace('‘', '').replace('’', '').replace('“', '').replace('”', '').replace('`', '')
        lines = [ln.strip() for ln in re.split(r'[\r\n]+', t) if ln.strip()]
        headers = {}
        i = 0
        while i < len(lines):
            ln = lines[i]
            m = re.match(r'^([^:]+):\s*(.*)$', ln)
            if m:
                name = m.group(1).strip()
                val = m.group(2).strip()
                if not val and i + 1 < len(lines):
                    nxt = lines[i+1]
                    if not re.match(r'^([^:]+):\s*', nxt):
                        val = nxt.strip()
                        i += 1
                headers[name] = val
            else:
                name = ln.strip()
                val = ''
                if i + 1 < len(lines):
                    nxt = lines[i+1].strip()
                    if re.match(r'^([^:]+):\s*(.*)$', nxt):
                        headers[name] = ''
                    else:
                        val = nxt
                        i += 1
                        headers[name] = val
            i += 1
        # sanitize pseudo headers and canonicalize
        canon = {}
        def title_case(h):
            parts = [p for p in re.split(r'-', h.strip()) if p]
            return '-'.join(p[:1].upper()+p[1:].lower() for p in parts)
        for k, v in headers.items():
            kk = k.strip()
            if not kk:
                continue
            if kk.startswith(':'):
                if kk.lower() == ':authority':
                    canon['Host'] = v
                # drop other HTTP/2 pseudo headers
                continue
            canon[title_case(kk)] = v
        return json.dumps(canon, ensure_ascii=False)
    except Exception:
        return s

def headers_pretty_text(json_str):
    try:
        import json
        obj = json.loads(json_str) if json_str else {}
        for _ in range(2):
            if isinstance(obj, str):
                obj = json.loads(obj)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return json_str or ''

def mask_key(k):
    try:
        s = (k or '').strip()
        if not s:
            return ''
        if len(s) <= 8:
            return '*' * len(s)
        return s[:4] + '...' + s[-4:]
    except Exception:
        return ''

def _normalize_api_base(base: str) -> str:
    try:
        b = (base or '').strip()
        if not b:
            return ''
        bl = b.lower()
        need_v1 = any(x in bl for x in ['openai.com', 'siliconflow.cn'])
        if need_v1 and not bl.rstrip('/').endswith('/v1'):
            return b.rstrip('/') + '/v1'
        return b
    except Exception:
        return base or ''

def _choose_ai_engine():
    try:
        eng = AiEngine.query.order_by(AiEngine.id.asc()).first()
        return eng
    except Exception:
        return None

def _llm_chat_json(messages, temperature=0, engine_id=None):
    eng = AiEngine.query.get(engine_id) if engine_id else _choose_ai_engine()
    if not eng:
        return {'error': '未配置AI引擎'}
    import requests
    base = _normalize_api_base((eng.api_base or '').strip())
    url = base.rstrip('/') + '/chat/completions'
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    key = (eng.api_key or '').strip()
    if key:
        headers['Authorization'] = 'Bearer ' + key
        headers['x-api-key'] = key
    msgs = list(messages)
    if (eng.persona or '').strip():
        persona_prompt = '你需要遵循以下人设：' + eng.persona.strip()
        msgs = [{'role':'system','content': persona_prompt}] + msgs
    payload = {
        'model': (eng.model_name or '').strip() or 'gpt-3.5-turbo',
        'temperature': temperature,
        'response_format': { 'type': 'json_object' },
        'messages': msgs,
        'max_tokens': 512
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=(10, 60))
        if r.status_code != 200:
            return {'error': f'LLM错误: {r.status_code}', 'preview': (r.text or '')[:160]}
        data = r.json() or {}
        content = (((data.get('choices') or [{}])[0]).get('message') or {}).get('content') or ''
        if not content:
            return {'error': 'LLM返回为空'}
        try:
            obj = json.loads(content)
            return {'result': obj}
        except Exception:
            return {'error': '解析LLM JSON失败', 'raw': content[:500]}
    except Exception as e:
        return {'error': str(e)}

def _llm_chat(messages, temperature=0, engine_id=None):
    eng = AiEngine.query.get(engine_id) if engine_id else _choose_ai_engine()
    if not eng:
        return {'error': '未配置AI引擎'}
    import requests
    base = _normalize_api_base((eng.api_base or '').strip())
    url = base.rstrip('/') + '/chat/completions'
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    key = (eng.api_key or '').strip()
    if key:
        headers['Authorization'] = 'Bearer ' + key
        headers['x-api-key'] = key
    msgs = list(messages)
    if (eng.persona or '').strip():
        persona_prompt = '你需要遵循以下人设：' + eng.persona.strip()
        msgs = [{'role':'system','content': persona_prompt}] + msgs
    payload = {
        'model': (eng.model_name or '').strip() or 'gpt-3.5-turbo',
        'temperature': temperature,
        'messages': msgs,
        'max_tokens': 512
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=(10, 60))
        if r.status_code != 200:
            return {'error': f'LLM错误: {r.status_code}', 'preview': (r.text or '')[:160]}
        data = r.json() or {}
        content = (((data.get('choices') or [{}])[0]).get('message') or {}).get('content') or ''
        if not content:
            return {'error': 'LLM返回为空'}
        return {'result_text': content, 'model': (eng.model_name or '').strip(), 'engine_id': eng.id}
    except Exception as e:
        return {'error': str(e)}

def _ai_tools_defs():
    return [
        {
            'type': 'function',
            'function': {
                'name': 'get_table_schema',
                'description': '获取collection_records表的字段信息',
                'parameters': { 'type': 'object', 'properties': {}, 'required': [] }
            }
        },
        {
            'type': 'function',
            'function': {
                'name': 'select_collection_records',
                'description': '查询collection_records，支持keyword模糊、最近days天与限制条数',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'keyword': { 'type': 'string' },
                        'days': { 'type': 'integer' },
                        'limit': { 'type': 'integer' }
                    },
                    'required': ['limit']
                }
            }
        }
    ]

def _execute_tool_call(name, args):
    try:
        if name == 'get_table_schema':
            return {
                'table': 'collection_records',
                'columns': ['id','keyword','title','summary','source','original_url','cover','deep_collected','deep_content','created_at']
            }
        if name == 'select_collection_records':
            kw = (args or {}).get('keyword') or ''
            days = int((args or {}).get('days') or 0)
            limit = int((args or {}).get('limit') or 10)
            base = CollectionRecord.query
            if kw and kw.strip():
                base = base.filter((CollectionRecord.title.ilike(f'%{kw}%')) | (CollectionRecord.summary.ilike(f'%{kw}%')))
            if days and days > 0:
                from datetime import datetime, timedelta
                since = datetime.utcnow() - timedelta(days=days)
                base = base.filter(CollectionRecord.created_at >= since)
            rows = base.order_by(CollectionRecord.created_at.desc()).limit(min(max(limit,1), 50)).all()
            items = []
            for r in rows:
                items.append({
                    'id': r.id,
                    'keyword': r.keyword,
                    'title': r.title,
                    'summary': (r.summary or ''),
                    'source': r.source,
                    'original_url': r.original_url,
                    'created_at': r.created_at.isoformat() if r.created_at else ''
                })
            return { 'items': items }
        return { 'error': f'未知工具: {name}' }
    except Exception as e:
        return { 'error': str(e) }

def _llm_chat_with_tools(messages, temperature=0, engine_id=None, max_steps=3):
    eng = AiEngine.query.get(engine_id) if engine_id else _choose_ai_engine()
    if not eng:
        return {'error': '未配置AI引擎'}
    import requests
    base = _normalize_api_base((eng.api_base or '').strip())
    url = base.rstrip('/') + '/chat/completions'
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    key = (eng.api_key or '').strip()
    if key:
        headers['Authorization'] = 'Bearer ' + key
        headers['x-api-key'] = key
    tools = _ai_tools_defs()
    history = list(messages)
    if (eng.persona or '').strip():
        persona_prompt = '你需要遵循以下人设：' + eng.persona.strip()
        history = [{'role':'system','content': persona_prompt}] + history
    for _ in range(max_steps):
        payload = {
            'model': (eng.model_name or '').strip() or 'gpt-3.5-turbo',
            'temperature': temperature,
            'messages': history,
            'tools': tools,
            'tool_choice': 'auto',
            'max_tokens': 512
        }
        try:
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=(10, 60))
            if r.status_code != 200:
                return {'error': f'LLM错误: {r.status_code}', 'preview': (r.text or '')[:200]}
            data = r.json() or {}
            msg = ((data.get('choices') or [{}])[0]).get('message') or {}
            tool_calls = msg.get('tool_calls') or []
            content = msg.get('content') or ''
            history.append({'role':'assistant','content': content, 'tool_calls': tool_calls})
            if tool_calls:
                for tc in tool_calls:
                    fn = (tc.get('function') or {})
                    name = fn.get('name') or ''
                    args_raw = fn.get('arguments') or '{}'
                    try:
                        args = json.loads(args_raw)
                    except Exception:
                        args = {}
                    result = _execute_tool_call(name, args)
                    history.append({'role':'tool','tool_call_id': tc.get('id') or '', 'content': json.dumps(result, ensure_ascii=False)})
                continue
            return {'result_text': content, 'model': (eng.model_name or '').strip(), 'engine_id': eng.id}
        except Exception as e:
            return {'error': str(e)}
    return {'error': '超过工具调用步数限制'}

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

@bp.route('/rules')
@login_required
@admin_required
def rules():
    rules = CollectionRule.query.order_by(CollectionRule.id.asc()).all()
    return render_template('admin/rules.html', rules=rules)

@bp.route('/ai_engines')
@login_required
@admin_required
def ai_engines():
    engines = AiEngine.query.order_by(AiEngine.id.asc()).all()
    return render_template('admin/ai_engines.html', engines=engines, mask_key=mask_key)

@bp.route('/ai_engines/add', methods=['POST'])
@login_required
@admin_required
def ai_engines_add():
    provider = (request.form.get('provider') or '').strip()
    api_base = (request.form.get('api_base') or '').strip()
    api_key = (request.form.get('api_key') or '').strip()
    model_name = (request.form.get('model_name') or '').strip()
    persona = (request.form.get('persona') or '').strip()
    if not api_base:
        flash('API地址不能为空')
        return redirect(url_for('admin.ai_engines'))
    eng = AiEngine(provider=provider, api_base=api_base, api_key=api_key, model_name=model_name, persona=persona)
    db.session.add(eng)
    db.session.commit()
    flash('AI引擎已添加')
    return redirect(url_for('admin.ai_engines'))

@bp.route('/ai_engines/edit/<int:id>', methods=['GET','POST'])
@login_required
@admin_required
def ai_engines_edit(id):
    eng = AiEngine.query.get_or_404(id)
    if request.method == 'POST':
        eng.provider = (request.form.get('provider') or '').strip()
        eng.api_base = (request.form.get('api_base') or '').strip()
        eng.api_key = (request.form.get('api_key') or '').strip()
        eng.model_name = (request.form.get('model_name') or '').strip()
        eng.persona = (request.form.get('persona') or '').strip()
        db.session.commit()
        flash('AI引擎已更新')
        return redirect(url_for('admin.ai_engines'))
    return render_template('admin/edit_ai_engine.html', eng=eng, display_key=mask_key(eng.api_key))

@bp.route('/ai_engines/delete/<int:id>')
@login_required
@admin_required
def ai_engines_delete(id):
    eng = AiEngine.query.get_or_404(id)
    db.session.delete(eng)
    db.session.commit()
    flash('AI引擎已删除')
    return redirect(url_for('admin.ai_engines'))

@bp.route('/ai_engines/test/<int:id>')
@login_required
@admin_required
def ai_engines_test(id):
    eng = AiEngine.query.get_or_404(id)
    import requests
    base = _normalize_api_base((eng.api_base or '').strip())
    url = base.rstrip('/') + '/chat/completions'
    headers = {'Accept': 'application/json'}
    if (eng.api_key or '').strip():
        headers['Authorization'] = 'Bearer ' + eng.api_key.strip()
        headers['x-api-key'] = eng.api_key.strip()
    payload = {
        'model': (eng.model_name or '').strip() or 'gpt-3.5-turbo',
        'messages': [{'role':'user','content':'ping'}],
        'max_tokens': 16,
        'temperature': 0
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=(10, 30))
        ok = (r.status_code == 200)
        return jsonify({'status': 'ok' if ok else 'error', 'code': r.status_code, 'preview': (r.text or '')[:160]})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 502

# AI 数据清洗与分析 DEMO
@bp.route('/ai_clean_demo')
@login_required
@admin_required
def ai_clean_demo():
    engines = AiEngine.query.order_by(AiEngine.id.asc()).all()
    return render_template('admin/ai_clean_demo.html', engines=engines)

@bp.route('/ai_clean_demo/run', methods=['POST'])
@login_required
@admin_required
def ai_clean_demo_run():
    engine_id = None
    instruction = ''
    if request.is_json:
        engine_id = request.json.get('engine_id')
        instruction = (request.json.get('instruction') or '').strip()
    else:
        engine_id = request.form.get('engine_id')
        instruction = (request.form.get('instruction') or '').strip()
    if not instruction:
        return jsonify({'status':'error','message':'分析指令不能为空'}), 400
    sys_prompt = '你是一个面向舆情数据的中文分析助手。请根据指令，对sqlite数据表 collection_records 的内容进行分析与总结。无需提供SQL，只需要以清晰的中文输出分析结论。'
    messages = [
        {'role':'system','content': sys_prompt},
        {'role':'user','content': instruction}
    ]
    resp = _llm_chat(messages, engine_id=engine_id)
    if resp.get('error'):
        return jsonify({'status':'error','message': resp.get('error'), 'preview': resp.get('preview')}), 502
    text = resp.get('result_text') or ''
    model_name = resp.get('model') or ''
    eng_id = resp.get('engine_id') or (engine_id or 0)
    rec = AiAnalysisResult(engine_id=eng_id, ai_model_name=model_name, instruction=instruction, result_text=text)
    db.session.add(rec)
    db.session.commit()
    return jsonify({'status':'ok','model': model_name, 'result_text': text, 'saved_id': rec.id})

@bp.route('/ai_clean_demo/history')
@login_required
@admin_required
def ai_clean_demo_history():
    try:
        limit_raw = request.args.get('limit') or '10'
        limit = int(limit_raw)
    except Exception:
        limit = 10
    limit = min(max(limit, 1), 50)
    rows = AiAnalysisResult.query.order_by(AiAnalysisResult.created_at.desc()).limit(limit).all()
    items = []
    for r in rows:
        items.append({
            'id': r.id,
            'engine_id': r.engine_id,
            'model': r.ai_model_name,
            'instruction': r.instruction or '',
            'result_text': r.result_text or '',
            'created_at': r.created_at.isoformat() if r.created_at else ''
        })
    return jsonify({'status':'ok','count': len(items), 'items': items})


@bp.route('/rules/add', methods=['POST'])
@login_required
@admin_required
def add_rule():
    site_name = (request.form.get('site_name') or '').strip()
    site = (request.form.get('site') or '').strip()
    title_xpath = request.form.get('title_xpath') or ''
    content_xpath = request.form.get('content_xpath') or ''
    headers_raw = request.form.get('headers_json') or ''
    headers_json = normalize_headers_text(headers_raw)
    if not site:
        flash('站点不能为空')
        return redirect(url_for('admin.rules'))
    exist = CollectionRule.query.filter_by(site=site).first()
    if exist:
        flash('该站点规则已存在，可前往编辑')
        return redirect(url_for('admin.rules'))
    rule = CollectionRule(site=site, site_name=site_name, title_xpath=title_xpath, content_xpath=content_xpath, headers_json=headers_json)
    db.session.add(rule)
    db.session.commit()
    flash('规则已添加')
    return redirect(url_for('admin.rules'))

@bp.route('/rules/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_rule(id):
    rule = CollectionRule.query.get_or_404(id)
    if request.method == 'POST':
        rule.site_name = (request.form.get('site_name') or '').strip()
        rule.site = (request.form.get('site') or '').strip()
        rule.title_xpath = request.form.get('title_xpath') or ''
        rule.content_xpath = request.form.get('content_xpath') or ''
        headers_raw = request.form.get('headers_json') or ''
        rule.headers_json = normalize_headers_text(headers_raw)
        db.session.commit()
        flash('规则已更新')
        return redirect(url_for('admin.rules'))
    headers_text = headers_pretty_text(rule.headers_json or '')
    return render_template('admin/edit_rule.html', rule=rule, headers_text=headers_text)

@bp.route('/rules/delete/<int:id>')
@login_required
@admin_required
def delete_rule(id):
    rule = CollectionRule.query.get_or_404(id)
    db.session.delete(rule)
    db.session.commit()
    flash('规则已删除')
    return redirect(url_for('admin.rules'))

@bp.route('/crawlers')
@login_required
@admin_required
def crawlers():
    rows = CrawlerSource.query.order_by(CrawlerSource.id.asc()).all()
    return render_template('admin/crawlers.html', crawlers=rows)

@bp.route('/crawlers/add', methods=['POST'])
@login_required
@admin_required
def crawlers_add():
    name = (request.form.get('name') or '').strip()
    key = (request.form.get('key') or '').strip()
    enabled = bool(request.form.get('enabled'))
    config_json = (request.form.get('config_json') or '').strip()
    if not key:
        flash('key 不能为空')
        return redirect(url_for('admin.crawlers'))
    row = CrawlerSource(name=name or key, key=key, enabled=enabled, config_json=config_json)
    db.session.add(row)
    db.session.commit()
    flash('爬虫已添加')
    return redirect(url_for('admin.crawlers'))

@bp.route('/crawlers/edit/<int:id>', methods=['GET','POST'])
@login_required
@admin_required
def crawlers_edit(id):
    row = CrawlerSource.query.get_or_404(id)
    if request.method == 'POST':
        row.name = (request.form.get('name') or '').strip()
        row.key = (request.form.get('key') or '').strip()
        row.enabled = bool(request.form.get('enabled'))
        row.config_json = (request.form.get('config_json') or '').strip()
        db.session.commit()
        flash('爬虫已更新')
        return redirect(url_for('admin.crawlers'))
    return render_template('admin/edit_crawler.html', row=row)

@bp.route('/crawlers/delete/<int:id>')
@login_required
@admin_required
def crawlers_delete(id):
    row = CrawlerSource.query.get_or_404(id)
    db.session.delete(row)
    db.session.commit()
    flash('爬虫已删除')
    return redirect(url_for('admin.crawlers'))

@bp.route('/crawlers/test/<int:id>')
@login_required
@admin_required
def crawlers_test(id):
    row = CrawlerSource.query.get_or_404(id)
    cfg = None
    try:
        cfg = json.loads(row.config_json or '{}')
    except Exception:
        cfg = None
    crawler = create_crawler(row.key, config=cfg)
    try:
        # 优先迭代获取以保证快速返回
        iter_fn = getattr(crawler, 'iter_data', None)
        items = []
        test_kw = '新闻'
        if callable(iter_fn):
            for it in iter_fn(test_kw, max_count=3):
                items.append(it)
                if len(items) >= 3:
                    break
        else:
            items = crawler.fetch_data(test_kw, max_count=3)
        formatted = crawler.to_display_schema(items)
        if not formatted:
            raise Exception('未解析到任何数据，请检查配置选择器或接口路径')
        return jsonify({'status':'ok','count':len(formatted), 'items': formatted})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500

@bp.route('/collector')
@login_required
@admin_required
def collector():
    rows = CrawlerSource.query.filter_by(enabled=True).order_by(CrawlerSource.id.asc()).all()
    # ensure built-ins present
    keys = set([r.key for r in rows])
    extras = []
    if 'baidu' not in keys:
        extras.append(type('T', (), {'key':'baidu','name':'百度新闻'})())
    if 'xinhua' not in keys:
        extras.append(type('T', (), {'key':'xinhua','name':'新华网'})())
    sources = list(rows) + extras
    return render_template('admin/collector.html', sources=sources)

@bp.route('/collector/run', methods=['POST'])
@login_required
@admin_required
def collector_run():
    data = request.get_json() or {}
    keyword = data.get('keyword', '').strip()
    max_count = int(data.get('max_count') or 20)
    source_key = (data.get('source') or 'baidu').lower()
    cfg = None
    src = CrawlerSource.query.filter_by(key=source_key).first()
    if src and (src.config_json or '').strip():
        try:
            cfg = json.loads(src.config_json)
        except Exception:
            cfg = None
    crawler = create_crawler(source_key, config=cfg) or BaiduCrawler()
    items = crawler.fetch_data(keyword, max_count=max_count)
    formatted = crawler.to_display_schema(items)
    for it in formatted:
        it['deep_collected'] = False
    return jsonify({
        'progress': 100,
        'keyword': keyword,
        'items': formatted,
        'source': source_key
    })

@bp.route('/collector/stream')
@login_required
@admin_required
def collector_stream():
    from flask import Response
    keyword = (request.args.get('keyword') or '').strip()
    max_count = int(request.args.get('max_count') or 20)
    source_key = (request.args.get('source') or 'baidu').lower()
    pace_ms = int(request.args.get('pace_ms') or 350)
    if pace_ms < 0:
        pace_ms = 0
    cfg = None
    src_row = CrawlerSource.query.filter_by(key=source_key).first()
    if src_row and (src_row.config_json or '').strip():
        try:
            cfg = json.loads(src_row.config_json)
        except Exception:
            cfg = None
    try:
        crawler = create_crawler(source_key, config=cfg)
    except Exception as e:
        def _err():
            yield f"event: error\ndata: {str(e)}\n\n"
        return Response(_err(), headers={'Content-Type':'text/event-stream','Cache-Control':'no-cache','X-Accel-Buffering':'no','Connection':'keep-alive'})
    def _gen():
        try:
            import time
            sent = 0
            yield f"event: status\ndata: 正在采集...\n\n"
            # 优先使用迭代接口
            iter_fn = getattr(crawler, 'iter_data', None)
            if callable(iter_fn):
                for it in iter_fn(keyword, max_count=max_count):
                    try:
                        formatted = crawler.to_display_schema([it])[0]
                    except Exception:
                        formatted = it
                    formatted['deep_collected'] = False
                    msg = json.dumps(formatted, ensure_ascii=False)
                    yield f"event: status\ndata: 正在采集{formatted.get('title','')}\n\n"
                    yield f"event: item\ndata: {msg}\n\n"
                    sent += 1
                    pct = max(0, min(99, round(100*sent/max_count)))
                    yield f"event: progress\ndata: {pct}\n\n"
                    if pace_ms:
                        time.sleep(pace_ms/1000.0)
                    if sent >= max_count:
                        break
            else:
                items = crawler.fetch_data(keyword, max_count=max_count)
                for it in items:
                    try:
                        formatted = crawler.to_display_schema([it])[0]
                    except Exception:
                        formatted = it
                    formatted['deep_collected'] = False
                    msg = json.dumps(formatted, ensure_ascii=False)
                    yield f"event: status\ndata: 正在采集{formatted.get('title','')}\n\n"
                    yield f"event: item\ndata: {msg}\n\n"
                    sent += 1
                    pct = max(0, min(99, round(100*sent/max_count)))
                    yield f"event: progress\ndata: {pct}\n\n"
                    if pace_ms:
                        time.sleep(pace_ms/1000.0)
            yield f"event: done\ndata: 已完成，共{sent}条\n\n"
        except Exception as e:
            err = str(e)
            yield f"event: error\ndata: {err}\n\n"
    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive'
    }
    return Response(_gen(), headers=headers)

@bp.route('/collector/deep', methods=['POST'])
@login_required
@admin_required
def collector_deep():
    data = request.get_json() or {}
    item = data.get('item') or {}
    url = (item.get('original_url') or '').strip()
    deep_content = ''
    try:
        if url.startswith('http://') or url.startswith('https://'):
            import requests
            from bs4 import BeautifulSoup
            import re
            r = requests.get(url, timeout=12, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9"
            })
            if r.status_code == 200:
                raw = r.content
                # 优先从响应头、HTML meta 与 apparent_encoding 推断编码
                enc = (r.encoding or '').lower()
                if not enc:
                    ct = r.headers.get('Content-Type') or ''
                    m2 = re.search(r"charset=([a-zA-Z0-9_-]+)", ct, re.I)
                    if m2:
                        enc = (m2.group(1) or '').lower()
                if not enc:
                    m = re.search(rb'charset=([a-zA-Z0-9_-]+)', raw[:8192], re.I)
                    if m:
                        try:
                            enc = m.group(1).decode('ascii', 'ignore').lower()
                        except Exception:
                            enc = ''
                if not enc:
                    try:
                        enc = (getattr(r, 'apparent_encoding', '') or '').lower()
                    except Exception:
                        enc = ''
                html = ''
                try:
                    from charset_normalizer import from_bytes
                    res = from_bytes(raw).best()
                    if res:
                        html = str(res)
                except Exception:
                    html = ''
                if not html:
                    for e in [enc, 'utf-8', 'gb18030', 'gbk', 'gb2312', 'big5']:
                        if not e:
                            continue
                        try:
                            html = raw.decode(e, errors='ignore')
                            break
                        except Exception:
                            continue
                    if not html:
                        html = raw.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html, 'html.parser')
                for t in soup(['script','style','noscript']):
                    t.decompose()
                candidates = []
                selectors = [
                    'article',
                    'div[role="article"]',
                    'div[id*="content"]',
                    'div[class*="content"]',
                    'div[id*="article"]',
                    'div[class*="article"]',
                    'div[id*="detail"]',
                    'div[class*="detail"]'
                ]
                for sel in selectors:
                    for el in soup.select(sel):
                        txt = el.get_text(separator='\n', strip=True)
                        if txt:
                            candidates.append(txt)
                if candidates:
                    candidates.sort(key=lambda x: len(x), reverse=True)
                    deep_content = candidates[0]
                else:
                    deep_content = soup.get_text(separator='\n', strip=True)
                # 保留必要的换行，清理不可见字符与重复空白
                deep_content = deep_content.replace('\u200b','').replace('\u200c','').replace('\u200d','')
                deep_content = re.sub(r'[\t\r]', ' ', deep_content)
                deep_content = re.sub(r'\n{3,}', '\n\n', deep_content)
                deep_content = re.sub(r'\s{2,}', ' ', deep_content)
                deep_content = deep_content.strip()[:15000]
                deep_content = fix_mojibake(deep_content)
    except Exception:
        deep_content = ''
    item['deep_content'] = deep_content or ''
    item['deep_collected'] = bool(item['deep_content'])
    return jsonify({'item': item})

@bp.route('/collector/save', methods=['POST'])
@login_required
@admin_required
def collector_save():
    payload = request.get_json() or {}
    keyword = payload.get('keyword', '')
    items = payload.get('items') or []
    saved_ids = []
    for it in items:
        rec = CollectionRecord(
            keyword=keyword,
            title=it.get('title') or '',
            summary=it.get('summary') or '',
            source=it.get('source') or '',
            original_url=it.get('original_url') or '',
            cover=it.get('cover') or '',
            deep_collected=bool((it.get('deep_content') or '').strip()),
            deep_content=(it.get('deep_content') or '')
        )
        db.session.add(rec)
        db.session.commit()
        saved_ids.append(rec.id)
    return jsonify({'saved_ids': saved_ids})

@bp.route('/data_warehouse')
@login_required
@admin_required
def data_warehouse():
    page = int(request.args.get('page') or 1)
    per_page = int(request.args.get('per_page') or 10)
    q = (request.args.get('q') or '').strip()
    src = (request.args.get('source') or '').strip()
    base_query = CollectionRecord.query
    if q:
        base_query = base_query.filter(
            (CollectionRecord.title.ilike(f'%{q}%')) |
            (CollectionRecord.summary.ilike(f'%{q}%'))
        )
    if src:
        base_query = base_query.filter(CollectionRecord.source == src)
    total = base_query.count()
    records = base_query.order_by(CollectionRecord.id.asc()).offset((page-1)*per_page).limit(per_page).all()
    return render_template('admin/data_warehouse.html', records=records, total=total, page=page, per_page=per_page, q=q, source=src)

@bp.route('/data_warehouse/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_record(id):
    record = CollectionRecord.query.get_or_404(id)
    if request.method == 'POST':
        record.title = request.form.get('title') or ''
        record.summary = request.form.get('summary') or ''
        record.source = request.form.get('source') or ''
        record.original_url = request.form.get('original_url') or ''
        record.cover = request.form.get('cover') or ''
        record.deep_content = request.form.get('deep_content') or ''
        record.deep_collected = bool(request.form.get('deep_collected'))
        db.session.commit()
        flash('记录已更新')
        return redirect(url_for('admin.data_warehouse'))
    return render_template('admin/edit_record.html', record=record)

@bp.route('/data_warehouse/delete/<int:id>')
@login_required
@admin_required
def delete_record(id):
    record = CollectionRecord.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()
    flash('记录已删除')
    return redirect(url_for('admin.data_warehouse'))


@bp.route('/data_warehouse/preview/<int:id>', methods=['GET'])
@login_required
@admin_required
def data_warehouse_preview(id):
    record = CollectionRecord.query.get_or_404(id)
    return jsonify({
        'status': 'ok',
        'id': record.id,
        'title': record.title or '',
        'source': record.source or '',
        'original_url': record.original_url or '',
        'deep_collected': bool(record.deep_collected),
        'deep_content': record.deep_content or ''
    })

def _parse_headers_dict(s):
    try:
        import json
        obj = json.loads(s) if s else {}
        for _ in range(2):
            if isinstance(obj, str):
                obj = json.loads(obj)
        if isinstance(obj, dict):
            return obj
        return {}
    except Exception:
        return {}

def _match_rule_for_record(record):
    src = (record.source or '').strip().lower()
    domain = urlparse(record.original_url or '').netloc.lower()
    candidates = CollectionRule.query.all()
    best = None
    for r in candidates:
        nm = (r.site_name or '').strip().lower()
        st = (r.site or '').strip().lower()
        if nm and nm in src:
            best = r
            break
        if st and st and (st in domain or domain.endswith(st)):
            best = r
    if best and domain and best.site and best.site.lower() not in domain:
        try:
            best.site = domain
            db.session.commit()
        except Exception:
            db.session.rollback()
    return best

def _extract_with_rule(url, rule):
    import requests
    html_text = ''
    headers = _parse_headers_dict(rule.headers_json or '')
    if 'User-Agent' not in headers:
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            html_text = resp.text
    except Exception:
        pass
    if not html_text:
        return {'title': '', 'content': ''}
    title_sel = rule.title_xpath or ''
    content_sel = rule.content_xpath or ''
    extracted = {'title': '', 'content': ''}
    try:
        from lxml import html as lxml_html
        doc = lxml_html.fromstring(html_text)
        if title_sel:
            t_nodes = doc.xpath(title_sel)
            if t_nodes:
                t = t_nodes[0]
                extracted['title'] = t.text_content().strip() if hasattr(t, 'text_content') else str(t).strip()
        if content_sel:
            c_nodes = doc.xpath(content_sel)
            if c_nodes:
                txts = []
                for n in c_nodes:
                    txts.append(n.text_content().strip() if hasattr(n, 'text_content') else str(n).strip())
                extracted['content'] = '\n\n'.join([t for t in txts if t])
    except Exception:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, 'html.parser')
        if not extracted['title']:
            tt = soup.find('title')
            extracted['title'] = (tt.get_text(strip=True) if tt else '')
        if not extracted['content']:
            art = soup.find('article') or soup.find(attrs={'id': re.compile('content|article|detail', re.I)}) or soup.find(attrs={'class': re.compile('content|article|detail', re.I)})
            if art:
                extracted['content'] = art.get_text('\n', strip=True)
            else:
                bod = soup.find('body')
                extracted['content'] = bod.get_text('\n', strip=True) if bod else ''
    extracted['title'] = re.sub(r"\s+", " ", extracted['title']).strip()
    return extracted

def _generic_extract(url):
    import requests, re
    from bs4 import BeautifulSoup
    html = ''
    try:
        resp = requests.get(url, timeout=20, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        })
        if resp.status_code == 200:
            raw = resp.content
            enc = (resp.encoding or '').lower()
            if not enc:
                ct = resp.headers.get('Content-Type') or ''
                m2 = re.search(r"charset=([a-zA-Z0-9_-]+)", ct, re.I)
                if m2:
                    enc = (m2.group(1) or '').lower()
            if not enc:
                m = re.search(rb'charset=([a-zA-Z0-9_-]+)', raw[:8192], re.I)
                if m:
                    try:
                        enc = m.group(1).decode('ascii', 'ignore').lower()
                    except Exception:
                        enc = ''
            if not enc:
                try:
                    from charset_normalizer import from_bytes
                    res = from_bytes(raw).best()
                    if res:
                        html = str(res)
                except Exception:
                    html = ''
            if not html:
                for e in [enc, 'utf-8', 'gb18030', 'gbk', 'gb2312', 'big5']:
                    if not e:
                        continue
                    try:
                        html = raw.decode(e, errors='ignore')
                        break
                    except Exception:
                        continue
                if not html:
                    html = raw.decode('utf-8', errors='ignore')
    except Exception:
        html = ''
    if not html:
        return {'title': '', 'content': ''}
    soup = BeautifulSoup(html, 'html.parser')
    for t in soup(['script','style','noscript']):
        t.decompose()
    candidates = []
    selectors = [
        'article',
        'div[role="article"]',
        'div[id*="content"]',
        'div[class*="content"]',
        'div[id*="article"]',
        'div[class*="article"]',
        'div[id*="detail"]',
        'div[class*="detail"]'
    ]
    for sel in selectors:
        for el in soup.select(sel):
            txt = el.get_text(separator='\n', strip=True)
            if txt:
                candidates.append(txt)
    if candidates:
        candidates.sort(key=lambda x: len(x), reverse=True)
        content = candidates[0]
    else:
        content = soup.get_text(separator='\n', strip=True)
    content = content.replace('\u200b','').replace('\u200c','').replace('\u200d','')
    content = re.sub(r'[\t\r]', ' ', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r'\s{2,}', ' ', content)
    content = content.strip()[:15000]
    tt = soup.find('title')
    title = (tt.get_text(strip=True) if tt else '')
    title = re.sub(r"\s+", " ", title).strip()
    return {'title': title, 'content': content}

@bp.route('/data_warehouse/deep_collect', methods=['POST'])
@login_required
@admin_required
def data_warehouse_deep_collect():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if isinstance(ids, str):
        try:
            ids = [int(x) for x in ids.split(',') if x.strip()]
        except Exception:
            ids = []
    updated = []
    failed = []
    if not ids:
        return jsonify({'status': 'ok', 'updated': [], 'failed': []})
    for rid in ids:
        try:
            rec = CollectionRecord.query.get(rid)
            if not rec or not (rec.original_url or '').strip():
                failed.append(rid)
                continue
            rule = _match_rule_for_record(rec)
            ext = None
            if rule:
                ext = _extract_with_rule(rec.original_url or '', rule)
                if not ext.get('content'):
                    try:
                        hdrs = _parse_headers_dict(rule.headers_json or '')
                        if 'User-Agent' not in hdrs:
                            hdrs['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
                            rule.headers_json = json.dumps(hdrs, ensure_ascii=False)
                            db.session.commit()
                    except Exception:
                        db.session.rollback()
            if not ext or not ext.get('content'):
                ext = _generic_extract(rec.original_url or '')
            rec.deep_content = ext.get('content') or ''
            if ext.get('title'):
                rec.title = ext.get('title')
            rec.deep_collected = bool(rec.deep_content)
            db.session.commit()
            if rec.deep_collected:
                updated.append(rid)
            else:
                failed.append(rid)
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            failed.append(rid)
    return jsonify({'status': 'ok', 'updated': updated, 'failed': failed})
