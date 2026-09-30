# -*- coding: utf-8 -*-
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from operations import backup


class Command(BaseCommand):
    help = 'Make the GitHub backup of the program and the database right now (see operations/backup.py).'

    def handle(self, *args, **options):
        cfg = backup.read_config()
        if cfg is None:
            raise CommandError(f'Бэкап не настроен: нет файла {backup.CONFIG_FILE}')
        base = Path(cfg['dir'])
        base.mkdir(parents=True, exist_ok=True)
        if not backup.run_backup(base):
            raise CommandError(f'Бэкап не удался, подробности в {base / "backup.log"}')
        backup.mark_success(base, timezone.localdate())
        backup._log(base, 'OK (вручную)')
        self.stdout.write(self.style.SUCCESS('Бэкап отправлен в GitHub'))
