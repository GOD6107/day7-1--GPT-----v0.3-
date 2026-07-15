# app/handlers/model_engine.py
from app.handlers.base import AdminBaseHandler
from app.models.model_engine import ModelRepository
from app.models.db import record_audit
from app.models.user import DialogueRepository
import json
import asyncio
import openai  # 新增依赖：pip install openai>=1.0.0

class AdminModelHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        page = int(self.get_argument("page", 1))
        keyword = self.get_argument("keyword", "")
        status = self.get_argument("status", "")
        models, total = ModelRepository.list_models(keyword, status, page)
        pages = (total + 5) // 6  # 每页6个
        self.render_page("admin/models.html", models=models, total=total, page=page, pages=pages,
                         keyword=keyword, status=status,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminModelCreateHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        data = {
            'code': self.get_body_argument("code", "").strip(),
            'name': self.get_body_argument("name", "").strip(),
            'provider': self.get_body_argument("provider", "").strip(),
            'model_name': self.get_body_argument("model_name", "").strip(),
            'base_url': self.get_body_argument("base_url", "").strip(),
            'api_key': self.get_body_argument("api_key", "").strip(),
            'category': self.get_body_argument("category", "text"),
            'system_prompt': self.get_body_argument("system_prompt", "").strip(),
            'top_value': float(self.get_body_argument("top_value", 0.8)),
            'context_count': int(self.get_body_argument("context_count", 8)),
            'is_default': int(self.get_body_argument("is_default", 0)),
            'status': self.get_body_argument("status", "active"),
        }
        ok = ModelRepository.create_model(data)
        record_audit("model_create", self.current_user['username'], self.client_ip(), data['code'])
        self.redirect(f"/admin/models?msg={'创建成功' if ok else '创建失败'}&msg_type={'success' if ok else 'error'}")

class AdminModelEditHandler(AdminBaseHandler):
    def post(self, model_id):
        if not self.require_admin(): return
        model_id = int(model_id)
        data = {
            'code': self.get_body_argument("code", "").strip(),
            'name': self.get_body_argument("name", "").strip(),
            'provider': self.get_body_argument("provider", "").strip(),
            'model_name': self.get_body_argument("model_name", "").strip(),
            'base_url': self.get_body_argument("base_url", "").strip(),
            'api_key': self.get_body_argument("api_key", "").strip(),
            'category': self.get_body_argument("category", "text"),
            'system_prompt': self.get_body_argument("system_prompt", "").strip(),
            'top_value': float(self.get_body_argument("top_value", 0.8)),
            'context_count': int(self.get_body_argument("context_count", 8)),
            'is_default': int(self.get_body_argument("is_default", 0)),
            'status': self.get_body_argument("status", "active"),
        }
        ok = ModelRepository.update_model(model_id, data)
        record_audit("model_edit", self.current_user['username'], self.client_ip(), f"id={model_id}")
        self.redirect(f"/admin/models?msg={'修改成功' if ok else '修改失败'}&msg_type={'success' if ok else 'error'}")

class AdminModelDeleteHandler(AdminBaseHandler):
    def post(self, model_id):
        if not self.require_admin(): return
        model_id = int(model_id)
        ok = ModelRepository.delete_model(model_id)
        record_audit("model_delete", self.current_user['username'], self.client_ip(), f"id={model_id}")
        self.redirect(f"/admin/models?msg={'删除成功' if ok else '删除失败'}&msg_type={'success' if ok else 'error'}")

class AdminModelDefaultHandler(AdminBaseHandler):
    def post(self, model_id):
        if not self.require_admin(): return
        model_id = int(model_id)
        ok = ModelRepository.set_default(model_id)
        record_audit("model_default", self.current_user['username'], self.client_ip(), f"id={model_id}")
        self.redirect(f"/admin/models?msg={'设为默认成功' if ok else '设置失败（可能已禁用）'}&msg_type={'success' if ok else 'error'}")

class AdminModelStatusHandler(AdminBaseHandler):
    def post(self, model_id):
        if not self.require_admin(): return
        model_id = int(model_id)
        status = self.get_body_argument("status", "active")
        ok = ModelRepository.set_status(model_id, status)
        record_audit("model_status", self.current_user['username'], self.client_ip(), f"id={model_id},status={status}")
        self.redirect(f"/admin/models?msg={'状态更新成功' if ok else '更新失败'}&msg_type={'success' if ok else 'error'}")

class AdminModelStreamHandler(AdminBaseHandler):
    async def get(self, model_id):
        if not self.require_admin():
            return

        message = self.get_argument("message", "你好")
        model = ModelRepository.get_model(int(model_id))

        # 如果指定模型不存在，则使用默认模型
        if not model:
            model = ModelRepository.get_default_model()
        if not model:
            self.write("无可用模型")
            return

        # 从模型配置中读取 API 参数
        base_url = model.get('base_url') or "https://aigc-api.aitoolcore.com/api/v1"
        api_key = model.get('api_key') or "sk-aigc-8228735868c270b1a6e8b88a08710483d9fa6e39"
        model_name = model.get('model_name') or "qwen3.7-plus"
        system_prompt = model.get('system_prompt') or ""
        temperature = model.get('top_value') or 0.8

        # 构造消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        # 设置 SSE 响应头
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")

        # 发送元信息（使用的模型名称）
        await self._send_event("meta", {"model": model_name})

        # 使用 OpenAI 异步客户端进行流式调用
        client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)

        try:
            stream = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=True,
                temperature=temperature,
                # 其他可选参数可从模型配置中扩展，如 top_p, max_tokens 等
            )

            # 逐块处理流式响应
            assembled_parts = []
            async for chunk in stream:
                delta = chunk.choices[0].delta
                # delta.content 可能是 None 或一个 ChatCompletionMessage — 取其字符串内容
                content_piece = ''
                try:
                    # 不同 SDK 版本/提供商可能在不同字段，兼容提取
                    if hasattr(delta, 'content'):
                        content_piece = delta.content or ''
                    elif isinstance(delta, dict):
                        content_piece = delta.get('content','') or delta.get('text','') or ''
                except Exception:
                    content_piece = str(delta)

                if content_piece:
                    assembled_parts.append(content_piece)
                    await self._send_event("delta", {"content": content_piece})

                # 若最后一个块带有 usage 信息，则发送并更新统计
                if getattr(chunk, 'usage', None):
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                    await self._send_event("usage", usage)
                    # 更新数据库中的 token 统计
                    ModelRepository.add_token_usage(
                        model['id'],
                        chunk.usage.prompt_tokens,
                        chunk.usage.completion_tokens
                    )

            full_text = ''.join(assembled_parts)
            # 保存本次测试对话到历史，确保保存的是字符串而非 SDK 对象
            try:
                DialogueRepository.save_history(self.current_user['id'], self.current_user['username'], message, full_text, response_type='ai', source=model_name, meta={'model': model_name})
            except Exception:
                pass

            await self._send_event("done", {})

        except Exception as e:
            error_msg = f"调用模型失败: {str(e)}"
            await self._send_event("error", {"message": error_msg})
            # 同时记录审计日志（可选）
            record_audit("model_stream_error", self.current_user['username'], self.client_ip(), error_msg)

    async def _send_event(self, event, data):
        """发送 SSE 事件（保持原样）"""
        self.write(f"event: {event}\n")
        self.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n")
        await self.flush()