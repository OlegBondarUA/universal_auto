# Generated by Django 4.1 on 2023-05-01 10:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0018_order_car_delivery_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='parksettings',
            name='description',
            field=models.CharField(max_length=255, null=True, verbose_name='Опиc'),
        ),
    ]