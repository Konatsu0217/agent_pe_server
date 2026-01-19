import jinja2
from pathlib import Path
from typing import Dict, Any

class TemplateEngine:
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """烘焙模板"""
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except jinja2.TemplateNotFound:
            print(f"Template not found: {template_name}")
            return ""
        except Exception as e:
            print(f"Error rendering template {template_name}: {e}")
            return ""

# 单例模式
_engine = None

def get_template_engine(templates_dir: str = "templates"):
    global _engine
    if _engine is None:
        _engine = TemplateEngine(templates_dir)
    return _engine
