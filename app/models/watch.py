from __future__ import annotations
import html as html_module
import json
import re
import urllib.request
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import quote, urljoin, urlparse
from app.models.db import get_connection

DEFAULT_REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://www.baidu.com/',
}

class SourceRepository:
    @staticmethod
    def list_sources(keyword='', status='', enabled=None, page=1, per_page=20):
        cond = []
        params = []
        if keyword:
            cond.append("(code LIKE ? OR name LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if status:
            cond.append("status=?")
            params.append(status)
        if enabled is not None:
            cond.append("enabled=?")
            params.append(1 if enabled else 0)
        where = "WHERE " + " AND ".join(cond) if cond else ""
        with get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM watch_sources {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM watch_sources {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                                params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def get_source(source_id):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM watch_sources WHERE id=?", (source_id,)).fetchone()

    @staticmethod
    def create_source(data):
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO watch_sources (code, name, url_template, headers_json, page_step, parser_type, enabled, status, description)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (data['code'], data['name'], data['url_template'], data.get('headers_json','{}'),
                      data.get('page_step',10), data.get('parser_type','generic'),
                      data.get('enabled',1), data.get('status','active'), data.get('description','')))
            return True
        except:
            return False

    @staticmethod
    def update_source(source_id, data):
        try:
            with get_connection() as conn:
                conn.execute("""
                    UPDATE watch_sources SET code=?, name=?, url_template=?, headers_json=?, page_step=?,
                    parser_type=?, enabled=?, status=?, description=?
                    WHERE id=?
                """, (data['code'], data['name'], data['url_template'], data.get('headers_json','{}'),
                      data.get('page_step',10), data.get('parser_type','generic'),
                      data.get('enabled',1), data.get('status','active'), data.get('description',''), source_id))
            return True
        except:
            return False

    @staticmethod
    def delete_source(source_id):
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM watch_sources WHERE id=?", (source_id,))
            return cur.rowcount > 0

    @staticmethod
    def set_enabled(source_id, enabled):
        with get_connection() as conn:
            conn.execute("UPDATE watch_sources SET enabled=? WHERE id=?", (1 if enabled else 0, source_id))
        return True

    @staticmethod
    def set_test_result(source_id, status, message):
        with get_connection() as conn:
            conn.execute("UPDATE watch_sources SET last_test_status=?, last_test_message=? WHERE id=?",
                         (status, message[:200], source_id))

class _LinkTextParser(HTMLParser):
    def __init__(self, base_url=None):
        super().__init__()
        self.base_url = base_url
        self.links = []
        self._current_link = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'a':
            return
        href = None
        for name, value in attrs:
            if name.lower() == 'href':
                href = value
                break
        if href:
            if self.base_url:
                href = urljoin(self.base_url, href)
            self._current_link = href
            self._current_text = []

    def handle_data(self, data):
        if self._current_link is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self._current_link is not None:
            title = ' '.join(''.join(self._current_text).split())
            if title:
                self.links.append((self._current_link, title))
            self._current_link = None
            self._current_text = []

class CollectorService:
    @staticmethod
    def _build_request(url, headers=None):
        final_headers = DEFAULT_REQUEST_HEADERS.copy()
        if headers:
            final_headers.update(headers)
        return urllib.request.Request(url, headers=final_headers)

    @staticmethod
    def _fetch_html(url, headers=None, timeout=8):
        try:
            jar = CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            req = CollectorService._build_request(url, headers)
            with opener.open(req, timeout=timeout) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                return html
        except Exception:
            return ''

    @staticmethod
    def _is_blocked_by_baidu(html):
        if not html:
            return False
        blocked_markers = ['访问安全验证', '安全验证', 'wappass.baidu.com', 'timeout-title', 'timeout-feedback']
        return any(marker in html for marker in blocked_markers)

    @staticmethod
    def _is_valid_link(href, title):
        if not href or not title:
            return False
        href = href.strip()
        if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            return False
        low_href = href.lower()
        low_title = title.lower()
        if 'login' in low_href or 'captcha' in low_href or 'javascript:void' in low_href:
            return False
        if any(block in low_title for block in ['备案', 'icp', '公安', '许可证', '增值电信', '京公网安备', '公示', '企业备案']):
            return False
        if len(title.strip()) < 3:
            return False
        return True

    @staticmethod
    def _is_relevant_link(href, title, keyword):
        if not keyword:
            return True
        keyword_lower = keyword.lower()
        if keyword_lower in title.lower():
            return True
        if keyword_lower in href.lower():
            return True
        return False

    @staticmethod
    def _filter_links_by_keyword(items, keyword):
        if not keyword:
            return items
        keyword_lower = keyword.lower()
        matched = [(href, title) for href, title in items if keyword_lower in title.lower() or keyword_lower in href.lower()]
        return matched if matched else items

    @staticmethod
    def _extract_links_generic(html, base_url=None):
        parser = _LinkTextParser(base_url=base_url)
        parser.feed(html)
        if parser.links:
            return [(href, title) for href, title in parser.links if CollectorService._is_valid_link(href, title)]

        links = []
        for href, title in re.findall(r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', html, re.S | re.I):
            href = html_module.unescape(href)
            title = html_module.unescape(re.sub(r'<[^>]+>', '', title)).strip()
            if base_url:
                href = urljoin(base_url, href)
            if CollectorService._is_valid_link(href, title):
                links.append((href, title))
        return links

    @staticmethod
    def _extract_baidu_news_links(html, base_url=None):
        links = []
        for href, title in re.findall(r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', html, re.S | re.I):
            if not href:
                continue
            href = html_module.unescape(href)
            if base_url:
                href = urljoin(base_url, href)
            normalized = href.lower()
            if '/link?url=' in normalized or 'baidu.com/link?url=' in normalized:
                title = html_module.unescape(re.sub(r'<[^>]+>', '', title)).strip()
                if title:
                    links.append((href, title))
        if links:
            return links
        return CollectorService._extract_links_generic(html, base_url)

    @staticmethod
    def _extract_bing_news_links(html, base_url=None):
        links = []
        for href, title in re.findall(r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', html, re.S | re.I):
            if not href:
                continue
            href = html_module.unescape(href)
            if href.startswith('//'):
                href = 'https:' + href
            if base_url:
                href = urljoin(base_url, href)
            if not href.startswith('http'):
                continue
            host = urlparse(href).netloc.lower()
            if any(host.endswith(domain) for domain in ['bing.com', 'microsoft.com', 'outlook.com', 'live.com', 'msn.com']):
                continue
            title = html_module.unescape(re.sub(r'<[^>]+>', '', title)).strip()
            if CollectorService._is_valid_link(href, title):
                links.append((href, title))
        return links

    @staticmethod
    def _build_search_attempts(source, keyword, page=1):
        step = (page - 1) * source.get('page_step', 10)
        attempts = []
        parser_type = source.get('parser_type', 'generic')
        title_keyword = quote(keyword)

        if parser_type == 'baidu_news':
            attempts.append((source['url_template'].replace('{keyword}', title_keyword).replace('{page_step}', str(step)), 'baidu_news'))
            attempts.append((f"https://www.bing.com/news/search?q={title_keyword}&first={step}", 'bing_news'))
            attempts.append((f"https://www.sogou.com/web?query={title_keyword}&page={page}", 'generic'))
        elif parser_type == 'bing_news':
            attempts.append((source['url_template'].replace('{keyword}', title_keyword).replace('{page_step}', str(step)), 'bing_news'))
            attempts.append((f"https://www.sogou.com/web?query={title_keyword}&page={page}", 'generic'))
            attempts.append((f"https://www.baidu.com/s?tn=news&ie=utf-8&word={title_keyword}&pn={step}", 'baidu_news'))
        else:
            attempts.append((source['url_template'].replace('{keyword}', title_keyword).replace('{page_step}', str(step)), parser_type))
        return attempts

    @staticmethod
    def _extract_links(html, base_url=None, parser_type='generic'):
        if parser_type == 'baidu_news':
            return CollectorService._extract_baidu_news_links(html, base_url)
        if parser_type == 'bing_news':
            return CollectorService._extract_bing_news_links(html, base_url)
        return CollectorService._extract_links_generic(html, base_url)

    @staticmethod
    def collect(keyword, source_ids, page=1, limit=12):
        sources = []
        with get_connection() as conn:
           base_sql = "SELECT * FROM watch_sources WHERE enabled=1 AND status='active'"
           if source_ids:
               placeholders = ','.join(['?'] * len(source_ids))
               sql = f"{base_sql} AND id IN ({placeholders})"
               rows = conn.execute(sql, source_ids).fetchall()
           else:
               rows = conn.execute(base_sql).fetchall()
           sources = [dict(row) for row in rows]

        results = []
        for source in sources:
           try:
               headers = json.loads(source.get('headers_json', '{}'))
               attempts = CollectorService._build_search_attempts(source, keyword, page)
               for url, attempt_parser_type in attempts:
                   html = CollectorService._fetch_html(url, headers=headers, timeout=8)
                   if not html:
                       continue
                   if CollectorService._is_blocked_by_baidu(html):
                       continue

                   items = CollectorService._extract_links(html, base_url=url, parser_type=attempt_parser_type)
                   if not items:
                       continue

                   filtered = [(href, title) for href, title in items if CollectorService._is_valid_link(href, title)]
                   filtered = CollectorService._filter_links_by_keyword(filtered, keyword)
                   for href, title in filtered:
                       if len(title) > 5 and href.startswith('http'):
                           results.append({
                               'source_id': source['id'],
                               'source_name': source['name'],
                               'keyword': keyword,
                               'title': title.strip(),
                               'url': href,
                               'summary': '',
                               'raw_json': '{}'
                           })
                   if filtered:
                       break
           except Exception:
               pass
        return results[:limit]

    @staticmethod
    def test_source(source, keyword='政务'):
        try:
            items = []
            headers = json.loads(source.get('headers_json', '{}'))
            for url, attempt_parser_type in CollectorService._build_search_attempts(source, keyword, 1):
               html = CollectorService._fetch_html(url, headers=headers, timeout=8)
               if not html:
                   continue
               if CollectorService._is_blocked_by_baidu(html):
                   continue
               items = CollectorService._extract_links(html, base_url=url, parser_type=attempt_parser_type)
               if items:
                   items = [(href, title) for href, title in items if CollectorService._is_valid_link(href, title)]
                   items = CollectorService._filter_links_by_keyword(items, keyword)
                   if items:
                       break
               html = CollectorService._fetch_html(url, headers=headers, timeout=8)
               if not html:
                   continue
               if CollectorService._is_blocked_by_baidu(html):
                   continue
               items = CollectorService._extract_links(html, base_url=url, parser_type=attempt_parser_type)
               if items:
                   items = [(href, title) for href, title in items if CollectorService._is_valid_link(href, title)]
                   items = CollectorService._filter_links_by_keyword(items, keyword)
                   if items:
                       break

            results = []
            for href, title in items:
               if len(title) > 5 and href.startswith('http'):
                   results.append({
                       'source_id': source.get('id', 0),
                       'source_name': source.get('name', ''),
                       'keyword': keyword,
                       'title': title.strip(),
                       'url': href,
                       'summary': '',
                       'raw_json': '{}'
                   })
            if not results:
                return [], '当前已尝试备用搜索引擎，但仍未获取到有效资源'
            return results[:12], f"测试解析到{len(results)}条"
        except Exception as e:
            return [], str(e)

class WarehouseRepository:
    @staticmethod
    def save_items(items):
        count = 0
        with get_connection() as conn:
            for item in items:
                try:
                    conn.execute("""
                        INSERT INTO warehouse_items (source_id, source_name, keyword, title, url, summary, raw_json)
                        VALUES (?,?,?,?,?,?,?)
                    """, (item.get('source_id',0), item.get('source_name',''), item.get('keyword',''),
                          item['title'], item['url'], item.get('summary',''), item.get('raw_json','{}')))
                    count += 1
                except:
                    pass
        return count

    @staticmethod
    def list_items(keyword='', deep_collected=None, page=1, per_page=20):
        cond = []
        params = []
        if keyword:
            cond.append("(title LIKE ? OR keyword LIKE ? OR source_name LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        if deep_collected is not None:
            cond.append("deep_collected=?")
            params.append(1 if deep_collected else 0)
        where = "WHERE " + " AND ".join(cond) if cond else ""
        with get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM warehouse_items {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM warehouse_items {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                                params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def delete_item(item_id):
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM warehouse_items WHERE id=?", (item_id,))
            return cur.rowcount > 0

    @staticmethod
    def bulk_delete(ids):
        if not ids: return 0
        placeholders = ','.join(['?']*len(ids))
        with get_connection() as conn:
            cur = conn.execute(f"DELETE FROM warehouse_items WHERE id IN ({placeholders})", ids)
            return cur.rowcount

    @staticmethod
    def mark_deep(item_id):
        with get_connection() as conn:
            conn.execute("UPDATE warehouse_items SET deep_collected=1, deep_data='预留深度数据' WHERE id=?", (item_id,))
        return True