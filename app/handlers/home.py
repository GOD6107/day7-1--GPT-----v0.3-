from app.handlers.base import BaseHandler

class IndexHandler(BaseHandler):
    def get(self):
        self.render_page("index.html")