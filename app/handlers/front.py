from __future__ import annotations
import csv
import json
from io import StringIO
from app.handlers.base import BaseHandler
from app.models.user import DialogueRepository, UserRepository
from app.models.watch import CollectorService, SourceRepository
from app.models.model_engine import ModelRepository
from app.models.db import record_audit
import openai


class ChatHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.redirect('/login')
            return
        self.render_page('chat.html', query='', answer='', error=None)


class ChatSendHandler(BaseHandler):
    def post(self):
        if not self.current_user:
            self.redirect('/login')
            return
        query = self.get_body_argument('query', '').strip()
        if not query:
            self.render_page('chat.html', query=query, answer='', error='请输入内容后再发送')
            return

        answer = self.generate_answer(query)
        DialogueRepository.save_history(
            self.current_user['id'],
            self.current_user['username'],
            query,
            answer,
            response_type='chat',
            source='frontend_chat',
            meta={'module': 'chat'}
        )
        record_audit('user_chat', self.current_user['username'], self.client_ip(), query)
        self.render_page('chat.html', query=query, answer=answer, error=None)

    def generate_answer(self, query):
        # 内置规则处理
        if '天气' in query:
            return '请使用“数字员工”模块的天气查询功能，输入格式：@天气 成都'
        if '深度采集' in query or '采集' in query:
            return '请在“数字员工”模块中指定采集任务，例如：深度采集 成都 政务'

        # 尝试使用默认模型配置
        model = ModelRepository.get_default_model()
        if model and model.get('provider') and model.get('api_key'):
            return f"已将请求转给模型 {model.get('name')} 处理：{query}"
        return f"智能助手：我已收到您的问题“{query}”，当前版本暂时使用本地响应。"


class WorkerHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.redirect('/login')
            return
        sources, _ = SourceRepository.list_sources(status='active', enabled=True)
        self.render_page('worker.html', result=None, sources=sources, error=None)


class WorkerSendHandler(BaseHandler):
    def post(self):
        if not self.current_user:
            self.redirect('/login')
            return
        query = self.get_body_argument('query', '').strip()
        mode = self.get_body_argument('mode', 'assistant')
        if not query:
            self.render_page('worker.html', result=None, sources=[], error='请输入任务指令')
            return

        result = self.handle_worker_task(query, mode)
        record_audit('worker_task', self.current_user['username'], self.client_ip(), f'{mode}:{query}')
        self.render_page('worker.html', result=result, sources=SourceRepository.list_sources(status='active', enabled=True)[0], error=None)

    def handle_worker_task(self, query, mode):
        # 删除原有天气模拟逻辑：所有请求尽量直接调用 AI 模型处理

        if '深度采集' in query or '采集' in query:
            keyword = query.replace('深度采集', '').replace('采集', '').strip() or '政务'
            sources, _ = SourceRepository.list_sources(status='active', enabled=True)
            if not sources:
                return {'type': 'collection', 'title': '采集失败', 'data': [], 'message': '未配置可用瞭源'}
            source_ids = [source['id'] for source in sources]
            items = CollectorService.collect(keyword, source_ids, page=1)
            card = {
                'type': 'collection',
                'title': f'深度采集结果：{keyword}',
                'data': items,
                'count': len(items)
            }
            DialogueRepository.save_history(
                self.current_user['id'],
                self.current_user['username'],
                query,
                json.dumps(card, ensure_ascii=False),
                response_type='collection',
                source='worker_collection',
                meta=card
            )
            return card

        # 将通用指令转发给配置的模型（若存在），否则返回模拟文本
        model = ModelRepository.get_default_model()
        if model and model.get('api_key') and model.get('model_name'):
            try:
                # 设置 openai 客户端配置（支持自定义 base_url）
                # prepare api key and base
                api_key = model.get('api_key')
                if api_key and api_key.startswith('Bearer '):
                    api_key = api_key.split(' ', 1)[1]
                api_key = api_key
                base = model.get('base_url')
                system_prompt = model.get('system_prompt') or ''
                messages = []
                if system_prompt:
                    messages.append({'role': 'system', 'content': system_prompt})
                messages.append({'role': 'user', 'content': query})
                # 使用 openai>=1.0.0 的新客户端接口（兼容其他兼容 OpenAI 协议的提供商）
                # Create OpenAI client with provided credentials/back-end (openai >=2.x expects api_key/base_url)
                client_kwargs = {}
                if api_key:
                    client_kwargs['api_key'] = api_key
                if base:
                    client_kwargs['base_url'] = base.rstrip('/')
                client = openai.OpenAI(**client_kwargs)
                # 调用 chat completions
                resp = client.chat.completions.create(
                    model=model.get('model_name'),
                    messages=messages,
                    temperature=float(model.get('top_value') or 0.8),
                    timeout=15,
                )
                # 支持不同返回格式（兼容多家返回结构）
                def _extract_text_from_choice(choice):
                    try:
                        # dict-style
                        if isinstance(choice, dict):
                            msg = choice.get('message') or choice.get('delta') or {}
                            if isinstance(msg, dict):
                                content = msg.get('content') or msg.get('text') or ''
                            else:
                                content = str(msg)
                            if not content:
                                content = choice.get('text') or ''
                            return str(content)

                        # object-style
                        msg = getattr(choice, 'message', None) or getattr(choice, 'delta', None)
                        if msg is not None:
                            if isinstance(msg, dict):
                                content = msg.get('content') or msg.get('text') or ''
                            else:
                                content = getattr(msg, 'content', None) or getattr(msg, 'text', None)
                                if content is None:
                                    content = ''
                            return str(content)

                        text_val = getattr(choice, 'text', None)
                        if text_val is not None:
                            return str(text_val)

                        return str(choice)
                    except Exception:
                        return str(choice)

                content = ''
                try:
                    first = None
                    if isinstance(resp, dict):
                        choices = resp.get('choices')
                        if choices:
                            first = choices[0]
                    else:
                        choices = getattr(resp, 'choices', None)
                        if choices:
                            first = choices[0]
                    if first is not None:
                        content = _extract_text_from_choice(first)
                    if not content:
                        # try to join all choices if available
                        all_texts = []
                        if isinstance(resp, dict):
                            for c in resp.get('choices', []) or []:
                                all_texts.append(_extract_text_from_choice(c))
                        else:
                            chs = getattr(resp, 'choices', None)
                            if chs:
                                for c in chs:
                                    all_texts.append(_extract_text_from_choice(c))
                        content = '\n'.join([t for t in all_texts if t]) or str(resp)
                except Exception:
                    content = str(resp)
                text = content or f'模型 {model.get("name")} 未返回内容'
                card = {'type': 'assistant', 'title': '数字员工响应', 'data': {'text': text}}
                DialogueRepository.save_history(
                    self.current_user['id'],
                    self.current_user['username'],
                    query,
                    text,
                    response_type='ai',
                    source=model.get('code') or 'model',
                    meta={'model': model.get('name'), 'model_id': model.get('id')}
                )
                return card
            except Exception as e:
                # 记录错误并回退到模拟回复
                DialogueRepository.save_history(
                    self.current_user['id'],
                    self.current_user['username'],
                    query,
                    f'模型调用异常: {str(e)}',
                    response_type='error',
                    source='worker_ai',
                    meta={'error': str(e)}
                )
                return {'type': 'assistant', 'title': '数字员工响应', 'data': {'text': f'模型调用异常: {str(e)}'}}

        # 未配置模型时返回错误提示（移除所有模拟返回）
        return {
            'type': 'assistant',
            'title': '数字员工响应',
            'data': {
                'text': '未配置可用模型或模型不可用，请在后台模型管理中添加/启用模型。'
            }
        }


class HistoryHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.redirect('/login')
            return
        page = int(self.get_argument('page', 1))
        histories, total = DialogueRepository.list_history(self.current_user['id'], page)
        pages = (total + 19) // 20
        self.render_page('history.html', histories=histories, page=page, pages=pages, total=total)


class ReportHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.redirect('/login')
            return
        counts = DialogueRepository.report_counts(self.current_user['id'])
        self.render_page('report.html', counts=counts)


class ReportExportHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.redirect('/login')
            return
        export_format = self.get_argument('format', 'csv')
        histories, _ = DialogueRepository.list_history(self.current_user['id'], page=1, per_page=1000)
        if export_format == 'json':
            self.set_header('Content-Type', 'application/json; charset=utf-8')
            self.set_header('Content-Disposition', 'attachment; filename="history.json"')
            self.write(json.dumps(histories, ensure_ascii=False, indent=2))
            return

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', '查询', '响应', '类型', '来源', '创建时间'])
        for row in histories:
            writer.writerow([row['id'], row['query'], row['response'], row['response_type'], row['source'], row['created_at']])
        self.set_header('Content-Type', 'text/csv; charset=utf-8')
        self.set_header('Content-Disposition', 'attachment; filename="history.csv"')
        self.write(output.getvalue())
