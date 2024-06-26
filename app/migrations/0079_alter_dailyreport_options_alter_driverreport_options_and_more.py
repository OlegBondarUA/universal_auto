# Generated by Django 4.1 on 2024-01-22 12:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0078_remove_driverefficiency_accept_percent_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='dailyreport',
            options={'verbose_name': 'Денний звіт', 'verbose_name_plural': 'Денні звіти'},
        ),
        migrations.AlterModelOptions(
            name='driverreport',
            options={'base_manager_name': 'objects'},
        ),
        migrations.AlterModelOptions(
            name='driverreshuffle',
            options={'verbose_name': 'Календар водіїв', 'verbose_name_plural': 'Календар водіїв'},
        ),
        migrations.AlterModelOptions(
            name='weeklyreport',
            options={'verbose_name': 'Тижневий звіт', 'verbose_name_plural': 'Тижневі звіти'},
        ),
        migrations.AlterField(
            model_name='investor',
            name='investors_partner',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='app.partner', verbose_name='Партнер'),
        ),
        migrations.AlterField(
            model_name='manager',
            name='managers_partner',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='app.partner', verbose_name='Партнер'),
        ),
    ]
