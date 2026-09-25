import django.db.models.deletion
from django.db import migrations, models
import django.db.models.functions.text


def fill_room_company(apps, schema_editor):
    """D2: copy company from the room's branch."""
    Room = apps.get_model('org', 'Room')
    for room in Room.objects.select_related('branch').all():
        room.company_id = room.branch.company_id
        room.save(update_fields=['company'])


def rename_duplicate_branches(apps, schema_editor):
    """D1: branches with the same name (case-insensitive) inside a company get a numeric suffix."""
    Branch = apps.get_model('org', 'Branch')
    seen = set()
    for branch in Branch.objects.order_by('company_id', 'id'):
        key = (branch.company_id, branch.name.strip().lower())
        if key not in seen:
            seen.add(key)
            continue
        n = 2
        while (branch.company_id, f'{branch.name} ({n})'.lower()) in seen:
            n += 1
        branch.name = f'{branch.name} ({n})'
        branch.save(update_fields=['name'])
        seen.add((branch.company_id, branch.name.lower()))


class Migration(migrations.Migration):

    dependencies = [
        ('org', '0006_remove_company_balance_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='company',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='org.company',
            ),
        ),
        migrations.RunPython(fill_room_company, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='room',
            name='company',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='org.company',
            ),
        ),
        migrations.RunPython(rename_duplicate_branches, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='branch',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('name'), models.F('company'),
                name='uniq_branch_name_per_company',
            ),
        ),
    ]
