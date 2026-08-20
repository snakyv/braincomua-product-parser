"""Creates the initial Product model for the parser project."""
# Initial schema for the Brain.com.ua product data pipeline.
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "parser_method",
                    models.CharField(
                        choices=[
                            ("requests_bs4", "Requests + BeautifulSoup"),
                            ("selenium", "Selenium"),
                            ("playwright", "Playwright"),
                        ],
                        max_length=32,
                    ),
                ),
                ("full_name", models.TextField(blank=True, null=True)),
                ("color", models.CharField(blank=True, max_length=255, null=True)),
                ("memory", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "manufacturer",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "regular_price",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                (
                    "sale_price",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                ("image_urls", models.JSONField(blank=True, null=True)),
                (
                    "product_code",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                ("reviews_count", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "screen_diagonal",
                    models.CharField(blank=True, max_length=128, null=True),
                ),
                (
                    "display_resolution",
                    models.CharField(blank=True, max_length=128, null=True),
                ),
                ("characteristics", models.JSONField(blank=True, null=True)),
            ],
            options={"ordering": ["id"]},
        ),
    ]
