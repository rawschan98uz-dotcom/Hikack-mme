from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_honorific_teacherbranch'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='staff_role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ceo', 'CEO'),
                    ('administrator', 'Administrator'),
                    ('branch_director', 'Branch director'),
                    ('limited_admin', 'Limited admin'),
                    ('marketer', 'Marketer'),
                    ('cashier', 'Cashier'),
                ],
                default='',
                max_length=32,
            ),
        ),
    ]
