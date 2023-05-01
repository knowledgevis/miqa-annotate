# Generated by Django 3.2.16 on 2023-01-19 19:41

import uuid

from django.core.management import call_command
from django.db import migrations, models
import django.db.models.deletion


def ingest_settings(apps, schema_editor):
    call_command('loaddata', 'setting.json')


class Migration(migrations.Migration):
    replaces = [
        ('core', '0036_setting_settingsgroup'),
        ('core', '0037_project_artifact_group'),
        ('core', '0038_project_model_mapping_group'),
        ('core', '0039_auto_20221207_2028'),
        ('core', '0040_auto_20221207_2037'),
        ('core', '0041_auto_20221208_1429'),
        ('core', '0042_auto_20230110_1852'),
        ('core', '0043_alter_setting_group'),
        ('core', '0044_alter_project_artifact_group'),
        ('core', '0045_auto_20230110_2004'),
        ('core', '0046_alter_setting_group'),
        ('core', '0047_alter_setting_type'),
        ('core', '0048_auto_20230113_1751'),
        ('core', '0049_alter_project_models_group'),
        ('core', '0050_delete_settingsgroup'),
        ('core', '0051_alter_setting_type'),
        ('core', '0052_alter_setting_type'),
        ('core', '0053_auto_20230119_1815'),
        ('core', '0054_auto_20230119_1938'),
    ]

    dependencies = [
        ('core', '0035_allow_null_decision_creation_times'),
    ]

    operations = [
        migrations.CreateModel(
            name='Setting',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ('key', models.CharField(max_length=255)),
                ('value', models.TextField(blank=True)),
                ('is_type', models.BooleanField(blank=True, default=False)),
                (
                    'group',
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to=models.Q(
                            ('type__in', ['GST', 'GAOT', 'GAT', 'GDCT', 'GEFMMT', 'GEMPT', 'GEMT'])
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='setting_group',
                        to='core.setting',
                    ),
                ),
                (
                    'type',
                    models.CharField(
                        choices=[
                            ('AOT', 'Anatomy Orientation'),
                            ('AT', 'Artifact'),
                            ('DCT', 'Decision Choice'),
                            ('EFMMT', 'Evaluation File to Model Mapping'),
                            ('EMPT', 'Evaluation Model Prediction'),
                            ('EMT', 'Evaluation Model'),
                            ('ST', 'Scan'),
                            ('GIP', 'Global Import Path'),
                            ('GEP', 'Global Export Path'),
                            ('NS', 'Not Set'),
                            ('GAOT', 'Group of Anatomy Orientations'),
                            ('GAT', 'Group of Artifacts'),
                            ('GDCT', 'Group of Decision Choices'),
                            ('GEFMMT', 'Group of Evaluation File to Model Mappings'),
                            ('GEMPT', 'Group of Evaluation Model Predictions'),
                            ('GEMT', 'Group of Evaluation Models'),
                            ('GST', 'Group of Scans'),
                        ],
                        default='NS',
                        max_length=20,
                    ),
                ),
            ],
            options={
                'ordering': ('key',),
            },
        ),
        migrations.AddField(
            model_name='project',
            name='artifacts_group',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'type': 'GAT'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='artifacts_group',
                to='core.setting',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='files_to_models_group',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'type': 'GEFMMT'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='files_to_models_group',
                to='core.setting',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='models_group',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'type': 'GEMT'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='models_group',
                to='core.setting',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='predictions_group',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'type': 'GEMPT'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='predictions_group',
                to='core.setting',
            ),
        ),
        migrations.RunPython(ingest_settings, reverse_code=lambda x, y: None),
    ]
