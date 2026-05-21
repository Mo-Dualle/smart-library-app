from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0012_account_avatar_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="author",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to="authors/photos/"),
        ),
        migrations.AddField(
            model_name="category",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to="categories/photos/"),
        ),
    ]
