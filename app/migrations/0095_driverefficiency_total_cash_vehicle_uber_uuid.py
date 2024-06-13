# Generated by Django 4.1 on 2024-04-10 12:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0094_vehicle_investor_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverefficiency',
            name='total_cash',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Готівкою'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='uber_uuid',
            field=models.CharField(max_length=36, null=True, verbose_name='Ідентифікатор авто в Uber'),
        ),
    ]