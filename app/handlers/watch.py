# app/handlers/watch.py
from app.handlers.base import AdminBaseHandler
from app.models.watch import SourceRepository, CollectorService, WarehouseRepository
from app.models.db import record_audit
import json

# ---------- 瞭望管理 ----------
class AdminWatchHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        keyword = self.get_argument("keyword", "")
        page = int(self.get_argument("page", 1))
        collect = self.get_argument("collect", "") == "1"
        source_ids = [int(x) for x in self.get_arguments("source_ids") if x.isdigit()]
        sources, _ = SourceRepository.list_sources(status='active', enabled=True)
        results = []
        if collect and keyword and source_ids:
            results = CollectorService.collect(keyword, source_ids, page)
            for item in results:
                item['json_data'] = json.dumps(item, ensure_ascii=False)
            record_audit("watch_collect", self.current_user['username'], self.client_ip(), f"keyword={keyword}, count={len(results)}")
        # 为了传递选中状态，将 source_ids 转为 set
        selected = set(source_ids)
        self.render_page("admin/watch.html", keyword=keyword, sources=sources, results=results,
                         selected_ids=selected, page=page,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminWatchSaveHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        items_json = self.get_body_arguments("items")
        items = []
        for data in items_json:
            try:
                items.append(json.loads(data))
            except:
                pass
        count = WarehouseRepository.save_items(items)
        record_audit("watch_save", self.current_user['username'], self.client_ip(), f"saved {count}")
        self.redirect(f"/admin/watch?msg=保存了 {count} 条数据&msg_type=success")

# ---------- 瞭源管理 ----------
class AdminSourceHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        page = int(self.get_argument("page", 1))
        keyword = self.get_argument("keyword", "")
        status = self.get_argument("status", "")
        enabled = self.get_argument("enabled", None)
        if enabled in ('0','1'):
            enabled = bool(int(enabled))
        else:
            enabled = None
        sources, total = SourceRepository.list_sources(keyword, status, enabled, page)
        pages = (total + 19) // 20
        self.render_page("admin/sources.html", sources=sources, total=total, page=page, pages=pages,
                         keyword=keyword, status=status, enabled=enabled,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""),
                         test_items=[], test_source=None, test_keyword='', test_message='')

class AdminSourceCreateHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        data = {
            'code': self.get_body_argument("code", "").strip(),
            'name': self.get_body_argument("name", "").strip(),
            'url_template': self.get_body_argument("url_template", "").strip(),
            'headers_json': self.get_body_argument("headers_json", "{}"),
            'page_step': int(self.get_body_argument("page_step", 10)),
            'parser_type': self.get_body_argument("parser_type", "generic"),
            'enabled': int(self.get_body_argument("enabled", 1)),
            'status': self.get_body_argument("status", "active"),
            'description': self.get_body_argument("description", "").strip(),
        }
        ok = SourceRepository.create_source(data)
        record_audit("source_create", self.current_user['username'], self.client_ip(), data['code'])
        self.redirect(f"/admin/sources?msg={'创建成功' if ok else '创建失败'}&msg_type={'success' if ok else 'error'}")

class AdminSourceEditHandler(AdminBaseHandler):
    def post(self, source_id):
        if not self.require_admin(): return
        source_id = int(source_id)
        data = {
            'code': self.get_body_argument("code", "").strip(),
            'name': self.get_body_argument("name", "").strip(),
            'url_template': self.get_body_argument("url_template", "").strip(),
            'headers_json': self.get_body_argument("headers_json", "{}"),
            'page_step': int(self.get_body_argument("page_step", 10)),
            'parser_type': self.get_body_argument("parser_type", "generic"),
            'enabled': int(self.get_body_argument("enabled", 1)),
            'status': self.get_body_argument("status", "active"),
            'description': self.get_body_argument("description", "").strip(),
        }
        ok = SourceRepository.update_source(source_id, data)
        record_audit("source_edit", self.current_user['username'], self.client_ip(), f"id={source_id}")
        self.redirect(f"/admin/sources?msg={'修改成功' if ok else '修改失败'}&msg_type={'success' if ok else 'error'}")

class AdminSourceDeleteHandler(AdminBaseHandler):
    def post(self, source_id):
        if not self.require_admin(): return
        source_id = int(source_id)
        ok = SourceRepository.delete_source(source_id)
        record_audit("source_delete", self.current_user['username'], self.client_ip(), f"id={source_id}")
        self.redirect(f"/admin/sources?msg={'删除成功' if ok else '删除失败'}&msg_type={'success' if ok else 'error'}")

class AdminSourceToggleHandler(AdminBaseHandler):
    def post(self, source_id):
        if not self.require_admin(): return
        source_id = int(source_id)
        enabled = int(self.get_body_argument("enabled", 0))
        ok = SourceRepository.set_enabled(source_id, enabled)
        record_audit("source_toggle", self.current_user['username'], self.client_ip(), f"id={source_id},enabled={enabled}")
        self.redirect(f"/admin/sources?msg={'开关更新成功' if ok else '更新失败'}&msg_type={'success' if ok else 'error'}")

class AdminSourceTestHandler(AdminBaseHandler):
    def post(self, source_id):
        if not self.require_admin(): return
        source_id = int(source_id)
        test_keyword = self.get_body_argument("test_keyword", "政务").strip()
        # 简单测试：只采集第一页，返回结果数
        try:
            from app.models.watch import CollectorService
            source = SourceRepository.get_source(source_id)
            if not source:
                self.redirect("/admin/sources?msg=瞭源不存在&msg_type=error")
                return
            rows, msg = CollectorService.test_source(dict(source), test_keyword)
            SourceRepository.set_test_result(source_id, 'ok' if rows else 'warn', msg)
            record_audit("source_test", self.current_user['username'], self.client_ip(), f"id={source_id}, count={len(rows)}")

            page = 1
            keyword = ''
            status = ''
            enabled = None
            sources, total = SourceRepository.list_sources(keyword, status, enabled, page)
            pages = (total + 19) // 20
            self.render_page("admin/sources.html", sources=sources, total=total, page=page, pages=pages,
                             keyword=keyword, status=status, enabled=enabled,
                             msg=f"测试完成，解析到{len(rows)}条", msg_type='success' if rows else 'warn',
                             test_items=rows, test_source=source, test_keyword=test_keyword, test_message=msg)
        except Exception as e:
            self.redirect(f"/admin/sources?msg=测试异常: {str(e)}&msg_type=error")

# ---------- 数据仓库 ----------
class AdminWarehouseHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        page = int(self.get_argument("page", 1))
        keyword = self.get_argument("keyword", "")
        deep_collected = self.get_argument("deep_collected", None)
        if deep_collected in ('0','1'):
            deep_collected = bool(int(deep_collected))
        else:
            deep_collected = None
        items, total = WarehouseRepository.list_items(keyword, deep_collected, page)
        pages = (total + 19) // 20
        self.render_page("admin/warehouse.html", items=items, total=total, page=page, pages=pages,
                         keyword=keyword, deep_collected=deep_collected,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminWarehouseDeleteHandler(AdminBaseHandler):
    def post(self, item_id):
        if not self.require_admin(): return
        item_id = int(item_id)
        ok = WarehouseRepository.delete_item(item_id)
        record_audit("warehouse_delete", self.current_user['username'], self.client_ip(), f"id={item_id}")
        self.redirect(f"/admin/warehouse?msg={'删除成功' if ok else '删除失败'}&msg_type={'success' if ok else 'error'}")

class AdminWarehouseBulkHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        ids = [int(x) for x in self.get_body_arguments("ids") if x.isdigit()]
        if not ids:
            self.redirect("/admin/warehouse?msg=未选择数据&msg_type=error")
            return
        count = WarehouseRepository.bulk_delete(ids)
        record_audit("warehouse_bulk_delete", self.current_user['username'], self.client_ip(), f"count={count}")
        self.redirect(f"/admin/warehouse?msg=已删除 {count} 条&msg_type=success")

class AdminWarehouseDeepHandler(AdminBaseHandler):
    def post(self, item_id):
        if not self.require_admin(): return
        item_id = int(item_id)
        ok = WarehouseRepository.mark_deep(item_id)
        record_audit("warehouse_deep", self.current_user['username'], self.client_ip(), f"id={item_id}")
        self.redirect(f"/admin/warehouse?msg={'深度采集标记成功' if ok else '标记失败'}&msg_type={'success' if ok else 'error'}")