import os
import uuid
from pathlib import Path
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from pydantic import ValidationError
from .db import transaction, engine, ROOT
from .security import signing_key


def create_app(config=None):
    app=Flask(__name__,static_folder=None)
    app.config.update(SECRET_KEY=signing_key(),MAX_CONTENT_LENGTH=8*1024*1024,
                      SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('NEXUS_SECURE_COOKIE','0')=='1')
    if config:app.config.update(config)
    from .api import bp
    app.register_blueprint(bp)
    @app.get('/api/nexus/openapi.json')
    def openapi():
        from .openapi import document
        return jsonify(document(app))
    @app.before_request
    def identify():g.request_id=uuid.uuid4().hex
    @app.after_request
    def headers(response):
        response.headers['X-Request-ID']=g.request_id
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        if request.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response
    @app.errorhandler(ValidationError)
    def validation(error):return jsonify(error='参数格式错误',details=[{'field':'.'.join(str(v) for v in e['loc']),'message':e['msg']} for e in error.errors()]),400
    @app.errorhandler(ValueError)
    def bad(error):return jsonify(error=str(error)),400
    @app.errorhandler(HTTPException)
    def http(error):
        return jsonify(error={401:'请先登录',403:'权限不足',404:'资源不存在',409:'当前状态不允许此操作',413:'文件不能超过8MB',429:'操作过于频繁'}.get(error.code,error.description)),error.code
    @app.get('/health')
    def health():
        from sqlalchemy import text
        from .jobs import redis_connection
        with engine().connect() as db:db.execute(text('SELECT 1'))
        redis_connection().ping()
        return jsonify(status='ok',edition='nexus')
    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path=''):
        if path.startswith('api/'):return jsonify(error='接口不存在'),404
        folder=ROOT/'web/dist'
        if not (folder/'index.html').exists():return 'Nexus frontend not built',503
        file=(folder/path).resolve()
        if path and file.is_relative_to(folder.resolve()) and file.is_file():return send_from_directory(folder,path)
        return send_from_directory(folder,'index.html')
    return app
