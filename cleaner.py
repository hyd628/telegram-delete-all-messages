from time import sleep
from os import getenv
from datetime import datetime, timedelta

from pyrogram import Client
from pyrogram.raw.functions.messages import Search
from pyrogram.raw.types import InputPeerSelf, InputMessagesFilterEmpty
from pyrogram.raw.types.messages import ChannelMessages
from pyrogram.errors import FloodWait, UnknownError


API_ID = getenv('API_ID', None) or int(input('Enter your Telegram API id: '))
API_HASH = getenv('API_HASH', None) or input('Enter your Telegram API hash: ')

app = Client("client", api_id=API_ID, api_hash=API_HASH)
app.start()


class Cleaner:
    def __init__(self, chats=None, search_chunk_size=100, delete_chunk_size=100):
        self.chats = chats or []
        self.time = None
        if search_chunk_size > 100:
            # https://github.com/gurland/telegram-delete-all-messages/issues/31
            #
            # The issue is that pyrogram.raw.functions.messages.Search uses
            # pagination with chunks of 100 messages. Might consider switching
            # to search_messages, which handles pagination transparently.
            raise ValueError('search_chunk_size > 100 not supported')
        self.search_chunk_size = search_chunk_size
        self.delete_chunk_size = delete_chunk_size

    @staticmethod
    def chunks(l, n):
        """Yield successive n-sized chunks from l.
        https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks#answer-312464"""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    @staticmethod
    def get_all_chats():
        dialogs = app.get_dialogs(pinned_only=True)

        dialog_chunk = app.get_dialogs()
        while len(dialog_chunk) > 0:
            dialogs.extend(dialog_chunk)
            dialog_chunk = app.get_dialogs(offset_date=dialogs[-1].top_message.date-1)

        return [d.chat for d in dialogs]

    def select_groups(self):
        chats = self.get_all_chats()
        groups = [c for c in chats if c.type in ('group', 'supergroup')]

        print('Delete all your messages in')
        for i, group in enumerate(groups):
            print(f'  {i+1}. {group.title}')

        print(
            f'  {len(groups) + 1}. '
            '(!) DELETE ALL YOUR MESSAGES IN ALL OF THOSE GROUPS (!)\n'
        )

        nums_str = input('Insert option numbers (comma separated): ')
        nums = map(lambda s: int(s.strip()), nums_str.split(','))

        for n in nums:
            if not 1 <= n <= len(groups) + 1:
                print('Invalid option selected. Exiting...')
                exit(-1)

            if n == len(groups) + 1:
                print('\nTHIS WILL DELETE ALL YOUR MESSSAGES IN ALL GROUPS!')
                answer = input('Please type "I understand" to proceed: ')
                if answer.upper() != 'I UNDERSTAND':
                    print('Better safe than sorry. Aborting...')
                    exit(-1)
                self.chats = groups
                break
            else:
                self.chats.append(groups[n - 1])
        
        groups_str = ', '.join(c.title for c in self.chats)
        print(f'\nSelected {groups_str}.\n')

    def select_time(self):
        now = datetime.now()
        current_time = now.strftime("%m/%d/%Y, %H:%M:%S")
        print("Current system date and time is:", current_time)
        #cutoff is hardcoded to 30 days earlier than current system time
        cutoff_time = now - timedelta(days=30)
        cutoff_time_display = cutoff_time.strftime("%m/%d/%Y, %H:%M:%S")
        print("Message deletion cutoff time is set to be 30 days before the current system time, which is:", cutoff_time_display)
        answer = input('\nIf this cutoff time is correct, please type "Y" to proceed: ')
        if answer.upper() != 'Y':
            print('Better safe than sorry. Aborting...')
            exit(-1)
        self.time = int(datetime.timestamp(cutoff_time))

    def run(self):
        for chat in self.chats:
            peer = app.resolve_peer(chat.id)
            message_ids = []
            add_offset = 0

            while True:
                q = self.search_messages(peer, add_offset, self.time)
                message_ids.extend(msg.id for msg in q['messages'])
                messages_count = len(q['messages'])
                print(f'Found {messages_count} of messages in "{chat.title}" older than the selected time.')
                if messages_count < self.search_chunk_size:
                    break
                add_offset += self.search_chunk_size

            self.delete_messages(chat.id, message_ids)

    def delete_messages(self, chat_id, message_ids):
        print('\nThis will irreversibly delete ALL messages older than the cutoff time in the selected group(s).')
        answer = input('Please type "Y" to proceed: ')
        if answer.upper() != 'Y':
            print('Better safe than sorry. Aborting...')
            exit(-1)
        print(f'Deleting {len(message_ids)} messages with message IDs:')
        print(message_ids)
        for chunk in self.chunks(message_ids, self.delete_chunk_size):
            try:
                app.delete_messages(chat_id=chat_id, message_ids=chunk)
            except FloodWait as flood_exception:
                sleep(flood_exception.x)

    def search_messages(self, peer, add_offset, cutoff_date):
        print(f'Searching messages. OFFSET: {add_offset}')
        return app.send(
            Search(
                peer=peer,
                q='',
                filter=InputMessagesFilterEmpty(),
                min_date=0,
                max_date=cutoff_date,
                offset_id=0,
                add_offset=add_offset,
                limit=self.search_chunk_size,
                max_id=0,
                min_id=0,
                hash=0
                #from_id=InputPeerSelf()
            ),
            sleep_threshold=60
        )


if __name__ == '__main__':
    try:
        deleter = Cleaner()
        deleter.select_groups()
        deleter.select_time()
        deleter.run()
    except UnknownError as e:
        print(f'UnknownError occured: {e}')
        print('Probably API has changed, ask developers to update this utility')
    finally:
        app.stop()
