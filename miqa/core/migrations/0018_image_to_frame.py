# Generated by Django 3.2.8 on 2021-11-05 19:29
import uuid

from django.db import migrations, models
import django.db.models.deletion
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_remove_site'),
    ]

    operations = [
        migrations.CreateModel(
            name='Frame',
            fields=[
                (
                    'created',
                    django_extensions.db.fields.CreationDateTimeField(
                        auto_now_add=True, verbose_name='created'
                    ),
                ),
                (
                    'modified',
                    django_extensions.db.fields.ModificationDateTimeField(
                        auto_now=True, verbose_name='modified'
                    ),
                ),
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ('raw_path', models.CharField(max_length=500, unique=True)),
                ('frame_number', models.IntegerField(default=0)),
                (
                    'scan',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='frames',
                        to='core.scan',
                    ),
                ),
            ],
            options={
                'ordering': ['scan', 'frame_number'],
            },
        ),
        migrations.RemoveField(
            model_name='evaluation',
            name='image',
        ),
        migrations.DeleteModel(
            name='Image',
        ),
        migrations.AddField(
            model_name='evaluation',
            name='frame',
            field=models.ForeignKey(
                default=None, on_delete=django.db.models.deletion.PROTECT, to='core.frame'
            ),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name='frame',
            index=models.Index(
                fields=['scan', 'frame_number'], name='core_frame_scan_id_ea9adc_idx'
            ),
        ),
    ]
