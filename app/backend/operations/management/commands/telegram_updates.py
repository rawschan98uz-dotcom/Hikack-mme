# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand

from operations import notify


class Command(BaseCommand):
    help = 'Show Telegram chats that wrote to the bot, so you can copy chat_id into student profiles.'

    def handle(self, *args, **options):
        config = notify.load_config()
        token = config.get('bot_token', '')
        ok, me = notify.telegram_call(token, 'getMe', {})
        if not ok:
            self.stdout.write(self.style.ERROR(f'Bot error: {me}'))
            return
        self.stdout.write(f'Bot: @{me.get("username")} (id {me.get("id")})')
        ok, updates = notify.telegram_call(token, 'getUpdates', {})
        if not ok:
            self.stdout.write(self.style.ERROR(f'Updates error: {updates}'))
            return
        chats = {}
        for update in updates or []:
            message = (
                update.get('message')
                or update.get('edited_message')
                or update.get('channel_post')
            )
            if not message:
                continue
            chat = message.get('chat', {})
            if chat.get('id') is not None:
                chats[chat['id']] = chat
        if not chats:
            self.stdout.write(
                'No messages yet. Open the bot in Telegram, press Start / send any message, '
                'then run this command again.'
            )
            return
        for chat_id, chat in chats.items():
            name = ' '.join(filter(None, [chat.get('first_name'), chat.get('last_name')])) or chat.get('title') or '-'
            username = f"@{chat['username']}" if chat.get('username') else '-'
            self.stdout.write(f'chat_id={chat_id} | {name} | {username}')
