# Generated by Django 4.1 on 2024-04-30 06:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0095_driverefficiency_total_cash_vehicle_uber_uuid'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorder',
            name='fleet_distance',
            field=models.DecimalField(decimal_places=2, max_digits=6, null=True, verbose_name='Відстань в агрегаторі'),
        ),
        migrations.AddField(
            model_name='investor',
            name='payment_type',
            field=models.CharField(choices=[('MONTH', 'Місяць'), ('WEEK', 'Тиждень'), ('DAY', 'День')], default='WEEK', max_length=25, verbose_name='Періодичність платежів'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='rental_price',
            field=models.IntegerField(default=0, verbose_name='Ціна оренди авто'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='start_mileage',
            field=models.IntegerField(default=0, verbose_name='Корекційний пробіг авто'),
        ),
        migrations.AlterField(
            model_name='driverpayments',
            name='payment_type',
            field=models.CharField(choices=[('MONTH', 'Місяць'), ('WEEK', 'Тиждень'), ('DAY', 'День')], default='WEEK', max_length=20, verbose_name='Тип платежу'),
        ),
        migrations.AlterField(
            model_name='driverschemarate',
            name='period',
            field=models.CharField(choices=[('MONTH', 'Місяць'), ('WEEK', 'Тиждень'), ('DAY', 'День')], max_length=25, verbose_name='Період розрахунку'),
        ),
        migrations.AlterField(
            model_name='schema',
            name='salary_calculation',
            field=models.CharField(choices=[('MONTH', 'Місяць'), ('WEEK', 'Тиждень'), ('DAY', 'День')], default='WEEK', max_length=25, verbose_name='Період розрахунку зарплати'),
        ),
        migrations.AlterField(
            model_name='vehicle',
            name='investor_schema',
            field=models.CharField(blank=True, choices=[('Equal_share', 'Рівномірна'), ('Proportional', 'Пропорційна'), ('Rental', 'Оренда')], max_length=15, null=True, verbose_name='Схема інвестора'),
        ),
    ]