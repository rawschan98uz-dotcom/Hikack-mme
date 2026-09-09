# -*- coding: utf-8 -*-
import time

from django.core.management.base import BaseCommand

from operations import notify


class Command(BaseCommand):
    help = 'Run Telegram notification checks once (or continuously with --loop).'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Run continuously until Ctrl+C')

    def handle(self, *args, **options):
        if options['loop']:
            self.stdout.write('Loop mode - press Ctrl+C to stop')
            while True:
                self.stdout.write(str(notify.run_once()))
                time.sleep(60)
        else:
            self.stdout.write(str(notify.run_once()))
