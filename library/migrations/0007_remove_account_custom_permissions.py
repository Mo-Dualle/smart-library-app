from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0006_account_user_granular_permissions"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="account",
            options={
                "db_table": "account",
                "verbose_name": "user",
                "verbose_name_plural": "users",
            },
        ),
    ]
