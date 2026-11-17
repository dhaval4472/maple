from django.db import migrations

from mapleleaf_app.content import REVIEWS


def seed_reviews(apps, schema_editor):
    Review = apps.get_model("mapleleaf_app", "Review")
    if Review.objects.exists():
        return
    for index, review in enumerate(REVIEWS):
        Review.objects.create(
            author=review["author"],
            quote=review["quote"],
            rating=review["rating"],
            category=review["category"],
            category_label=review["category_label"],
            source_label=review["source_label"],
            is_published=True,
            display_order=index,
        )


def unseed_reviews(apps, schema_editor):
    Review = apps.get_model("mapleleaf_app", "Review")
    Review.objects.filter(author__in=[review["author"] for review in REVIEWS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("mapleleaf_app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_reviews, unseed_reviews),
    ]
