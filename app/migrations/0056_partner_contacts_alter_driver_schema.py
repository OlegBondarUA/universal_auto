# Generated by Django 4.1 on 2023-10-09 14:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0055_credentialpartner_driverpayments_driverschemarate_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='partner',
            name='contacts',
            field=models.BooleanField(default=False, verbose_name='Доступ до контактів'),
        ),
    ]