# Generated by Django 4.1 on 2023-05-23 07:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0023_order_client_message_id_order_driver_message_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='NinjaFleet',
            fields=[
                ('fleet_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.fleet')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('app.fleet',),
        ),
        migrations.AlterModelOptions(
            name='boltpaymentsorder',
            options={'verbose_name': 'Payments order: Bolt', 'verbose_name_plural': 'Payments order: Bolt'},
        ),
        migrations.AlterModelOptions(
            name='newuklonpaymentsorder',
            options={'verbose_name': 'Payments order: NewUklon', 'verbose_name_plural': 'Payments order: NewUklon'},
        ),
        migrations.AlterModelOptions(
            name='uberpaymentsorder',
            options={'verbose_name': 'Payments order: Uber', 'verbose_name_plural': 'Payments order: Uber'},
        ),
        migrations.AlterModelOptions(
            name='uklonpaymentsorder',
            options={'verbose_name': 'Payments order: Uklon', 'verbose_name_plural': 'Payments order: Uklon'},
        ),
        migrations.CreateModel(
            name='NinjaPaymentsOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_from', models.DateTimeField()),
                ('report_to', models.DateTimeField()),
                ('full_name', models.CharField(max_length=255)),
                ('chat_id', models.CharField(max_length=11)),
                ('total_rides', models.PositiveIntegerField()),
                ('total_distance', models.DecimalField(decimal_places=2, max_digits=10)),
                ('total_amount_cach', models.DecimalField(decimal_places=2, max_digits=10)),
                ('total_amount_on_card', models.DecimalField(decimal_places=2, max_digits=10)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Payments order: Ninja',
                'verbose_name_plural': 'Payments order: Ninja',
                'unique_together': {('report_from', 'report_to', 'full_name', 'chat_id')},
            },
        ),
    ]