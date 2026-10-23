from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sync", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="syncoperation",
            name="operation_type",
            field=models.CharField(max_length=100),
        ),
    ]
