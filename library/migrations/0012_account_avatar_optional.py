from django.db import migrations, models


def clear_missing_default_avatars(apps, schema_editor):
    Account = apps.get_model("library", "Account")
    Account.objects.filter(avatar="avatars/avatar.jpg").update(avatar=None)


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0011_restrict_user_manager_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="account",
            name="avatar",
            field=models.ImageField(blank=True, null=True, upload_to="avatars/"),
        ),
        migrations.RunPython(clear_missing_default_avatars, migrations.RunPython.noop),
    ]
