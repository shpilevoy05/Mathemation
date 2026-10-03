from django import template

from apps.web.permissions import is_expert, is_methodist


register = template.Library()
register.simple_tag(is_expert, name="is_expert")
register.simple_tag(is_methodist, name="is_methodist")
