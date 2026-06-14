from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0001_initial'),
        ('org', '0001_initial'),
        ('crm', '0004_course_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='group_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='group',
            name='room',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='groups',
                to='org.room',
            ),
        ),
        migrations.AddField(
            model_name='group',
            name='tags',
            field=models.ManyToManyField(blank=True, related_name='groups', to='operations.tag'),
        ),
    ]
