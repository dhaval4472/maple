from django.db import migrations
from django.db.models import Q


def backfill_master_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    StaffProfile = apps.get_model("mapleleaf_app", "StaffProfile")

    profiles = [
        StaffProfile(user_id=user.pk, role="master")
        for user in User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).iterator()
    ]
    if profiles:
        StaffProfile.objects.bulk_create(profiles, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("mapleleaf_app", "0004_staffprofile_workticket"),
    ]

    operations = [
        migrations.RunPython(backfill_master_profiles, migrations.RunPython.noop),
    ]
