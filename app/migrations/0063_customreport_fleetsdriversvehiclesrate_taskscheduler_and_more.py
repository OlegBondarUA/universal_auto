# Generated by Django 4.1 on 2023-11-30 16:14

import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0062_boltrequest_gpsnumber_uagpssynchronizer_uberrequest_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_from', models.DateTimeField(verbose_name='Звіт з')),
                ('report_to', models.DateTimeField(null=True, verbose_name='Звіт по')),
                ('vendor_name', models.CharField(default='Ninja', max_length=30, verbose_name='Агрегатор')),
                ('full_name', models.CharField(max_length=255, null=True, verbose_name='ПІ водія')),
                ('driver_id', models.CharField(max_length=50, null=True, verbose_name='Унікальний індифікатор водія')),
                ('total_amount_without_fee', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Чистий дохід')),
                ('total_amount_cash', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Готівкою')),
                ('total_amount_on_card', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='На картку')),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Загальна сума')),
                ('tips', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Чайові')),
                ('total_rides', models.PositiveIntegerField(default=0, null=True, verbose_name='Кількість поїздок')),
                ('total_distance', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Пробіг під замовленням')),
                ('bonuses', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Бонуси')),
                ('fee', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Комісія')),
                ('fares', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Штрафи')),
                ('cancels', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Плата за скасування')),
                ('compensations', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Компенсації')),
                ('refunds', models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Повернення коштів')),
                ('partner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='app.partner', verbose_name='Партнер')),
                ('vehicle', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='app.vehicle', verbose_name='Автомобіль')),
            ],
        ),
        migrations.CreateModel(
            name='TaskScheduler',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=75, verbose_name='Назва задачі')),
                ('task_time', models.TimeField(verbose_name='Час запуску задачі')),
                ('periodic', models.BooleanField(verbose_name='Періодичний запуск')),
                ('weekly', models.BooleanField(verbose_name='Тижнева задача')),
                ('interval', models.IntegerField(blank=True, null=True, verbose_name='Інтервал запуску')),
                ('arguments', models.IntegerField(blank=True, null=True, verbose_name='Аргументи')),
            ],
            options={
                'verbose_name': 'Розклад задач',
                'verbose_name_plural': 'Розклад задач',
            },
        ),
        migrations.RenameModel(
            old_name='Report_of_driver_debt',
            new_name='ReportDriveDebt',
        ),
        migrations.RenameModel(
            old_name='Fleets_drivers_vehicles_rate',
            new_name='FleetsDriversVehiclesRate',
        ),
        migrations.AddField(
            model_name='carefficiency',
            name='clean_kasa',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Чистий дохід'),
        ),
        migrations.AddField(
            model_name='carefficiency',
            name='report_to',
            field=models.DateTimeField(null=True, verbose_name='Звіт по'),
        ),
        migrations.AddField(
            model_name='driverefficiency',
            name='report_to',
            field=models.DateTimeField(null=True, verbose_name='Звіт по'),
        ),
        migrations.AddField(
            model_name='payments',
            name='report_to',
            field=models.DateTimeField(null=True, verbose_name='Звіт по'),
        ),
        migrations.AddField(
            model_name='rentinformation',
            name='report_to',
            field=models.DateTimeField(null=True, verbose_name='Звіт по'),
        ),
        migrations.AddField(
            model_name='summaryreport',
            name='report_to',
            field=models.DateTimeField(null=True, verbose_name='Звіт по'),
        ),
        migrations.AlterField(
            model_name='carefficiency',
            name='report_from',
            field=models.DateTimeField(verbose_name='Звіт з'),
        ),
        migrations.AlterField(
            model_name='driver',
            name='schema',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.schema', verbose_name='Схема роботи'),
        ),
        migrations.AlterField(
            model_name='driverefficiency',
            name='report_from',
            field=models.DateTimeField(verbose_name='Звіт з'),
        ),
        migrations.AlterField(
            model_name='payments',
            name='report_from',
            field=models.DateTimeField(verbose_name='Звіт з'),
        ),
        migrations.AlterField(
            model_name='payments',
            name='total_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Пробіг під замовленням'),
        ),
        migrations.AlterField(
            model_name='rentinformation',
            name='report_from',
            field=models.DateTimeField(verbose_name='Звіт з'),
        ),
        migrations.AlterField(
            model_name='schema',
            name='shift_time',
            field=models.TimeField(default=datetime.time(0, 0), verbose_name='Час проведення розрахунку'),
        ),
        migrations.AlterField(
            model_name='statuschange',
            name='driver',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='app.driver'),
        ),
        migrations.AlterField(
            model_name='summaryreport',
            name='report_from',
            field=models.DateTimeField(verbose_name='Звіт з'),
        ),
        migrations.AlterField(
            model_name='summaryreport',
            name='total_amount_without_fee',
            field=models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Чистий дохід'),
        ),
        migrations.AlterField(
            model_name='summaryreport',
            name='total_distance',
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name='Пробіг під замовленням'),
        ),
        migrations.AddField(
            model_name='driverreshuffle',
            name='partner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    to='app.partner', verbose_name='Партнер'),
        ),
        migrations.AlterField(
            model_name='fleetsdriversvehiclesrate',
            name='driver',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='app.driver',
                                    verbose_name='Водій'),
        ),
    ]