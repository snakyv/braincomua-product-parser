"""Admin registration for parser_app."""
from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "parser_method", "full_name", "product_code")
    search_fields = ("full_name", "product_code")
    list_filter = ("parser_method",)
