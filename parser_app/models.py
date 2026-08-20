"""Database models used by the brain.com.ua parsers."""
from django.db import models


class Product(models.Model):
    PARSER_METHOD_CHOICES = [
        ("requests_bs4", "Requests + BeautifulSoup"),
        ("selenium", "Selenium"),
        ("playwright", "Playwright"),
    ]

    parser_method = models.CharField(max_length=32, choices=PARSER_METHOD_CHOICES)
    full_name = models.TextField(null=True, blank=True)
    color = models.CharField(max_length=255, null=True, blank=True)
    memory = models.CharField(max_length=255, null=True, blank=True)
    manufacturer = models.CharField(max_length=255, null=True, blank=True)
    regular_price = models.CharField(max_length=64, null=True, blank=True)
    sale_price = models.CharField(max_length=64, null=True, blank=True)
    image_urls = models.JSONField(null=True, blank=True)
    product_code = models.CharField(max_length=64, null=True, blank=True)
    reviews_count = models.PositiveIntegerField(null=True, blank=True)
    screen_diagonal = models.CharField(max_length=128, null=True, blank=True)
    display_resolution = models.CharField(max_length=128, null=True, blank=True)
    characteristics = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.full_name or f"Product {self.pk}"
