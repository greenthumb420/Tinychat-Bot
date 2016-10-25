import logging
import random
import re
import threading
import getpass
import pinylib
from apis import youtube, soundcloud, lastfm, other, locals
from utilities import string_utili, media_manager, privacy_settings

CONFIG = {
    'prefix': '!',  # This is only needed for room commands, Private message to the bot uses no prefix.
    'key': 'g7gh8hg78',
    'super_key': 'fj092fjgjg75jkoa',
    'bot_msg_to_console': False,
    'auto_message_enabled': True,
    'public_cmds': True,
    'debug_to_file': False,
    'auto_message_interval': 360,
    'nick_bans': 'nick_bans.txt',
    'account_bans': 'account_bans.txt',
    'ban_strings': 'ban_strings.txt',
    'debug_file_name': 'tinybot_debug.log'
}

log = logging.getLogger(__name__)
__version__ = '1.0.5'


class TinychatBot(pinylib.TinychatRTMPClient):
    key = CONFIG['key']
    is_cmds_public = CONFIG['public_cmds']
    is_newusers_allowed = True
    is_broadcasting_allowed = True
    is_guest_entry_allowed = True
    is_guest_nicks_allowed = False
    privacy_settings = object
    # Media related.
    media_manager = media_manager.MediaManager()
    media_timer_thread = None
    search_list = []

    def on_join(self, join_info_dict):
        log.info('User join info: %s' % join_info_dict)
        user = self.add_user_info(join_info_dict)

        if join_info_dict['account']:
            tc_info = pinylib.tinychat.tinychat_user_info(join_info_dict['account'])
            if tc_info is not None:
                user.tinychat_id = tc_info
                user.last_login = tc_info['last_active']
            if join_info_dict['own']:
                self.console_write(pinylib.COLOR['red'], 'Room Owner %s:%d:%s' %
                                   (join_info_dict['nick'], join_info_dict['id'], join_info_dict['account']))
            elif join_info_dict['mod']:
                self.console_write(pinylib.COLOR['bright_red'], 'Moderator %s:%d:%s' %
                                   (join_info_dict['nick'], join_info_dict['id'], join_info_dict['account']))
            else:
                self.console_write(pinylib.COLOR['bright_yellow'], '%s:%d has account: %s' %
                                   (join_info_dict['nick'], join_info_dict['id'], join_info_dict['account']))

                badaccounts = pinylib.fh.file_reader(self.config_path(), CONFIG['account_bans'])
                if badaccounts is not None:
                    if join_info_dict['account'] in badaccounts:
                        if self._is_client_mod:
                            self.send_ban_msg(join_info_dict['nick'], join_info_dict['id'])
                            self.send_forgive_msg(join_info_dict['id'])
                            self.send_bot_msg('*Auto-Banned:* (bad account)')
        else:
            if join_info_dict['id'] is not self._client_id:
                if not self.is_guest_entry_allowed:
                    self.send_ban_msg(join_info_dict['nick'], join_info_dict['id'])
                    # self.send_forgive_msg(join_info_dict['id'])
                    self.send_bot_msg('*Auto-Banned:* (guests not allowed)')
                else:
                    self.console_write(pinylib.COLOR['cyan'], '%s:%d joined the room.' %
                                       (join_info_dict['nick'], join_info_dict['id']))

    def on_joinsdone(self):
        if not self._is_reconnected:
            if CONFIG['auto_message_enabled']:
                self.start_auto_msg_timer()
        if self._is_client_mod:
            self.send_banlist_msg()
        if self._is_client_owner and self._room_type != 'default':
            threading.Thread(target=self.get_privacy_settings).start()

    def on_avon(self, uid, name):
        if not self.is_broadcasting_allowed:
            self.send_close_user_msg(name)
            self.console_write(pinylib.COLOR['cyan'], 'Auto closed broadcast %s:%s' % (name, uid))
        else:
            self.console_write(pinylib.COLOR['cyan'], '%s:%s is broadcasting.' % (name, uid))

    def on_nick(self, old, new, uid):
        old_info = self.find_user_info(old)
        old_info.nick = new
        if old in self._room_users.keys():
            del self._room_users[old]
            self._room_users[new] = old_info

        if str(old).startswith('guest-'):
            if self._client_id != uid:

                if str(new).startswith('guest-'):
                    if self._is_client_mod:
                        if not self.is_guest_nicks_allowed:
                            self.send_ban_msg(new, uid)
                            self.send_bot_msg('*Auto-Banned:* (bot nick detected)')

                if str(new).startswith('newuser'):
                    if self._is_client_mod:
                        if not self.is_newusers_allowed:
                            self.send_ban_msg(new, uid)
                            self.send_bot_msg('*Auto-Banned:* (wanker detected)')

                else:
                    bn = pinylib.fh.file_reader(self.config_path(), CONFIG['nick_bans'])
                    if bn is not None and new in bn:
                        if self._is_client_mod:
                            self.send_ban_msg(new, uid)
                            self.send_bot_msg('*Auto-Banned:* (bad nick)')

                    else:
                        user = self.find_user_info(new)
                        if user is not None:
                            if user.account:
                                self.send_bot_msg('*Greetings & Welcome to ' + self._roomname + '* - ' + new + ' ('
                                                  + user.account + ')')
                            else:
                                self.send_bot_msg('*Greetings & Welcome to ' + self._roomname + '* - ' + new)

                        if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                            if not self.media_manager.is_mod_playing:
                                self.send_media_broadcast_start(self.media_manager.track().type,
                                                                self.media_manager.track().id,
                                                                time_point=self.media_manager.elapsed_track_time(),
                                                                private_nick=new)
        self.console_write(pinylib.COLOR['bright_cyan'], '%s:%s changed nick to: %s' % (old, uid, new))

    # Media Events.
    def on_media_broadcast_start(self, media_type, video_id, usr_nick):
        """
        A user started a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param video_id: str the youtube ID or soundcloud track ID.
        :param usr_nick: str the user name of the user playing media. NOTE: replace with self.user_obj.nick
        """
        if media_type == 'youTube':
            _youtube = youtube.youtube_time(video_id, check=False)
            if _youtube is not None:
                self.media_manager.mb_start(self.user.nick, _youtube)

        elif media_type == 'soundCloud':
            _soundcloud = soundcloud.soundcloud_track_info(video_id)
            if _soundcloud is not None:
                self.media_manager.mb_start(self.user.nick, _soundcloud)

        self.media_event_timer(self.media_manager.track().time)
        self.console_write(pinylib.COLOR['bright_magenta'], '%s is playing %s %s' %
                           (usr_nick, media_type, video_id))

    def on_media_broadcast_close(self, media_type, usr_nick):
        """
        A user closed a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param usr_nick: str the user name of the user closing the media.
        """
        self.cancel_media_event_timer()
        self.media_manager.mb_close()
        self.console_write(pinylib.COLOR['bright_magenta'], '%s closed the %s' % (usr_nick, media_type))

    def on_media_broadcast_paused(self, media_type, usr_nick):
        """
        A user paused the media broadcast.
        :param media_type: str the type of media being paused. youTube or soundCloud.
        :param usr_nick: str the user name of the user pausing the media.
        """
        self.cancel_media_event_timer()
        self.media_manager.mb_pause()
        self.console_write(pinylib.COLOR['bright_magenta'], '%s paused the %s' % (usr_nick, media_type))

    def on_media_broadcast_play(self, media_type, time_point, usr_nick):
        """
        A user resumed playing a media broadcast.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user resuming the tune.
        """
        self.cancel_media_event_timer()
        new_media_time = self.media_manager.mb_play(time_point)
        self.media_event_timer(new_media_time)

        self.console_write(pinylib.COLOR['bright_magenta'], '%s resumed the %s at: %s' %
                           (usr_nick, media_type, self.format_time(time_point)))

    def on_media_broadcast_skip(self, media_type, time_point, usr_nick):
        """
        A user time searched a tune.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user time searching the tune.
        """
        self.cancel_media_event_timer()
        new_media_time = self.media_manager.mb_skip(time_point)
        if not self.media_manager.is_paused:
            self.media_event_timer(new_media_time)

        self.console_write(pinylib.COLOR['bright_magenta'], '%s time searched the %s at: %s' %
                           (usr_nick, media_type, self.format_time(time_point)))

    # Media Message Method.
    def send_media_broadcast_start(self, media_type, video_id, time_point=0, private_nick=None):
        """
        Starts a media broadcast.
        NOTE: This method replaces play_youtube and play_soundcloud
        :param media_type: str 'play' or 'playsc'
        :param video_id: str the media video ID.
        :param time_point: int where to start the media from in milliseconds.
        :param private_nick: str if not None, start the media broadcast for this username only.
        """
        mbs_msg = '/mbs %s %s %s' % (media_type, video_id, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbs_msg)
        else:
            self.send_chat_msg(mbs_msg)

    # Message Method.
    def send_bot_msg(self, msg, use_chat_msg=False):
        """
        Send a chat message to the room.
        NOTE: If the client is moderator, send_owner_run_msg will be used.
        If the client is not a moderator, send_chat_msg will be used.
        Setting use_chat_msg to True, forces send_chat_msg to be used.
        """
        if use_chat_msg:
            self.send_chat_msg(msg)
        else:
            if self._is_client_mod:
                self.send_owner_run_msg(msg)
            else:
                self.send_chat_msg(msg)
        if CONFIG['bot_msg_to_console']:
            self.console_write(pinylib.COLOR['white'], msg)

    # Command Handler.
    def message_handler(self, msg_sender, decoded_msg):
        """ Public and Moderator commands. """
        if decoded_msg.startswith(CONFIG['prefix']):
            parts = decoded_msg.split(' ')
            cmd = parts[0].lower().strip()
            cmd_arg = ' '.join(parts[1:]).strip()

            # Owner and super mod commands.
            if self.user.is_owner or self.user.is_super:
                if cmd == CONFIG['prefix'] + 'kill':
                    self.do_kill()

                elif cmd == CONFIG['prefix'] + 'reboot':
                    self.do_reboot()
            # Public Commands (if enabled).
            if self.is_cmds_public or self.user.is_owner or self.user.is_super \
                    or self.user.is_mod or self.user.has_power:

                if cmd == CONFIG['prefix'] + 'fullscreen':
                    self.do_fullscreen()

                elif cmd == CONFIG['prefix'] + 'who?':
                    self.do_who_plays()

                elif cmd == CONFIG['prefix'] + 'help':
                    self.do_help()

                elif cmd == CONFIG['prefix'] + 'uptime':
                    self.do_uptime()

                elif cmd == CONFIG['prefix'] + 'pmme':
                    self.do_pmme()

                elif cmd == CONFIG['prefix'] + 'status':
                    self.do_playlist_status()

                elif cmd == CONFIG['prefix'] + 'next?':
                    self.do_next_tune_in_playlist()

                elif cmd == CONFIG['prefix'] + 'now?':
                    self.do_now_playing()

                elif cmd == CONFIG['prefix'] + 'play':
                    threading.Thread(target=self.do_play_youtube, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'playsc':
                    threading.Thread(target=self.do_play_soundcloud, args=(cmd_arg,)).start()

                # Special Features
                elif cmd == CONFIG['prefix'] + 'spy':
                    threading.Thread(target=self.do_spy, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'spyuser':
                    threading.Thread(target=self.do_account_spy, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'urban':
                    threading.Thread(target=self.do_search_urban_dictionary, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'weather':
                    threading.Thread(target=self.do_weather_search, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'advice':
                    threading.Thread(target=self.do_advice).start()

                elif cmd == CONFIG['prefix'] + 'time':
                    threading.Thread(target=self.do_time, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'translate':
                    threading.Thread(target=self.do_translate, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'whois':
                    threading.Thread(target=self.do_whois_ip, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'chuck':
                    threading.Thread(target=self.do_chuck_norris).start()

                elif cmd == CONFIG['prefix'] + '8ball':
                    threading.Thread(target=self.do_8ball, args=(cmd_arg,)).start()

                # Moderator controls for main chat, Also work via private message to the bot.
                elif cmd == CONFIG['prefix'] + 'top':
                    threading.Thread(target=self.do_lastfm_chart, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'random':
                    threading.Thread(target=self.do_lastfm_random_tunes, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'tag':
                    threading.Thread(target=self.search_lastfm_by_tag, args=(cmd_arg,)).start()

                elif cmd == CONFIG['prefix'] + 'skip':
                    self.do_skip()

                elif cmd == CONFIG['prefix'] + 'pause':
                    self.do_media_pause()

                elif cmd == CONFIG['prefix'] + 'resume':
                    self.do_play_media()

                elif cmd == CONFIG['prefix'] + 'stop':
                    self.do_close_media()

            self.console_write(pinylib.COLOR['yellow'], msg_sender + ': ' + cmd + ' ' + cmd_arg)
        else:
            self.console_write(pinylib.COLOR['green'], msg_sender + ': ' + decoded_msg)

            if self._is_client_mod:
                threading.Thread(target=self.check_msg_for_bad_string, args=(decoded_msg,)).start()
        self.user.last_msg = decoded_msg

    # == Super Mod Commands Methods. ==
    def do_make_mod(self, account):
        """
        Make a tinychat account a room moderator.
        :param account str the account to make a moderator.
        """
        if self._is_client_owner:
            if self.user.is_super:
                if len(account) is 0:
                    self.send_private_msg('*Missing account name.*', self.user.nick)
                else:
                    tc_user = self.privacy_settings.make_moderator(account)
                    if tc_user is None:
                        self.send_private_msg('*The account is invalid.*', self.user.nick)
                    elif not tc_user:
                        self.send_private_msg('*The account is already a moderator.*', self.user.nick)
                    elif tc_user:
                        self.send_private_msg('*' + account + ' was made a room moderator.*', self.user.nick)
            else:
                if self.user.is_mod:
                    self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    def do_remove_mod(self, account):
        """
        Removes a tinychat account from the moderator list.
        :param account str the account to remove from the moderator list.
        """
        if self._is_client_owner:
            if self.user.is_super:
                if len(account) is 0:
                    self.send_private_msg('*Missing account name.*', self.user.nick)
                else:
                    tc_user = self.privacy_settings.remove_moderator(account)
                    if tc_user:
                        self.send_private_msg('*' + account + ' is no longer a room moderator.*', self.user.nick)
                    elif not tc_user:
                        self.send_private_msg('*' + account + ' is not a room moderator.*', self.user.nick)
        else:
            if self.user.is_mod:
                self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    def do_directory(self):
        """ Toggles if the room should be shown on the directory. """
        if self._is_client_owner:
            if self.user.is_super:
                if self.privacy_settings.show_on_directory():
                    self.send_private_msg('*Room is now shown on the Tinychat directory.*', self.user.nick)
                else:
                    self.send_private_msg('*Room is not shown on the Tinychat directory.*', self.user.nick)
            else:
                if self.user.is_mod:
                    self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    def do_push2talk(self):
        """ Toggles if the room should be in push2talk mode. """
        if self._is_client_owner:
            if self.user.is_super:
                if self.privacy_settings.set_push2talk():
                    self.send_private_msg('*Push2Talk is now enabled.*', self.user.nick)
                else:
                    self.send_private_msg('*Push2Talk is now disabled.*', self.user.nick)
            else:
                if self.user.is_mod:
                    self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    def do_green_room(self):
        """ Toggles if the room should be in greenroom mode. """
        if self._is_client_owner:
            if self.user.is_super:
                if self.privacy_settings.set_greenroom():
                    self.send_private_msg('*Green room is now enabled.*', self.user.nick)
                else:
                    self.send_private_msg('*Green room is now disabled.*', self.user.nick)
            else:
                if self.user.is_mod:
                    self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    def do_clear_room_bans(self):
        """ Clear all room bans. """
        if self._is_client_owner:
            if self.user.is_super:
                if self.privacy_settings.clear_bans():
                    self.send_private_msg('*All room bans were cleared.*', self.user.nick)
            else:
                if self.user.is_mod:
                    self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    def do_nick(self, new_nick):
        """
        Set a new nick for the bot.
        :param new_nick: str the new nick.
        """
        if self.user.is_owner or self.user.is_super:
            if len(new_nick) is 0:
                self.client_nick = string_utili.create_random_string(3, 36)
                self.set_nick()
            else:
                if re.match("^[][{}a-zA-Z0-9_]{1,36}$", new_nick):
                    self.client_nick = new_nick
                    self.set_nick()
                    self.send_private_msg('Nickname changed to ' + new_nick, self.user.nick)
        else:
            if self.user.is_mod:
                self.send_private_msg('*This is only available to Owner/super users.*', self.user.nick)

    # == Owner And Super Mod Command Methods. ==
    def do_kill(self):
        """ Kills the bot. """
        self.disconnect()

    def do_reboot(self):
        """ Reboots the bot. """
        self.reconnect()

    def do_room_settings(self):
        """ Shows current room settings. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            settings = self.privacy_settings.current_settings()
            self.send_private_msg('*Broadcast Password:* ' + settings['broadcast_pass'], self.user.nick)
            self.send_private_msg('*Room Password:* ' + settings['room_pass'], self.user.nick)
            self.send_private_msg('*Login Type:* ' + settings['allow_guests'], self.user.nick)
            self.send_private_msg('*Directory:* ' + settings['show_on_directory'], self.user.nick)
            self.send_private_msg('*Push2Talk:* ' + settings['push2talk'], self.user.nick)
            self.send_private_msg('*Greenroom:* ' + settings['greenroom'], self.user.nick)
        else:
            self.send_private_msg('Command not available for normal users.', self.user.nick)

    # Owner and Mod Commands Methods.
    def do_media_info(self):
        """ Shows basic media info. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            self.send_private_msg('*Track List Index:* ' + str(self.media_manager.track_list_index), self.user.nick)
            self.send_private_msg('*Playlist Length:* ' + str(len(self.media_manager.track_list)), self.user.nick)
            self.send_private_msg('*Current Time Point:* ' +
                                  self.format_time(self.media_manager.elapsed_track_time()), self.user.nick)
            self.send_private_msg('*Active Threads:* ' + str(threading.active_count()), self.user.nick)
            self.send_private_msg('*Is Mod Playing:* ' + str(self.media_manager.is_mod_playing), self.user.nick)
        else:
            self.send_private_msg('Command is not available for normal users.', self.user.nick)

    def do_lastfm_chart(self, chart_items):
        """
        Makes a playlist from the currently most played tunes on last.fm
        :param chart_items: int the amount of tunes we want.
        """
        if self.user.has_power or self.user.is_mod or self.user.is_owner or self.user.is_super:
            if chart_items is 0 or chart_items is None:
                self.send_private_msg('Please specify the amount of tunes you want.', self.user.nick)
            else:
                try:
                    _items = int(chart_items)
                except ValueError:
                    self.send_private_msg('Only numbers allowed.', self.user.nick)
                else:
                    if 0 < _items < 30:
                        self.send_private_msg('Please wait while creating a playlist...', self.user.nick)
                        self.send_bot_msg('Please wait while creating a playlist...', self.user.nick)
                        last = lastfm.get_lastfm_chart(_items)
                        if last is not None:
                            if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                                self.media_manager.add_track_list(self.user.nick, last)
                                self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm chart.*',
                                                      self.user.nick)
                            else:
                                self.media_manager.add_track_list(self.user.nick, last)
                                self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm chart.*',
                                                      self.user.nick)
                                track = self.media_manager.get_next_track()
                                self.send_media_broadcast_start(track.type, track.id)
                                self.media_event_timer(track.time)
                        else:
                            self.send_private_msg('Failed to retrieve a result from last.fm.', self.user.nick)
                    else:
                        self.send_private_msg('No more than 30 tunes.', self.user.nick)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_lastfm_random_tunes(self, max_tunes):
        """
        Creates a playlist from what other people are listening to on last.fm.
        :param max_tunes: int the max amount of tunes.
        """
        if self.user.has_power or self.user.is_mod or self.user.is_owner or self.user.is_super:
            if max_tunes is 0 or max_tunes is None:
                self.send_private_msg('Please specify the max amount of tunes you want.', self.user.nick)
            else:
                try:
                    _items = int(max_tunes)
                except ValueError:
                    self.send_private_msg('Only numbers allowed.', self.user.nick)
                else:
                    if 0 < _items < 50:
                        self.send_private_msg('Please wait while creating a playlist...', self.user.nick)
                        last = lastfm.lastfm_listening_now(max_tunes)
                        if last is not None:
                            if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                                self.media_manager.add_track_list(self.user.nick, last)
                                self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm*',
                                                      self.user.nick)
                            else:
                                self.media_manager.add_track_list(self.user.nick, last)
                                self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm*',
                                                      self.user.nick)
                                track = self.media_manager.get_next_track()
                                self.send_media_broadcast_start(track.type, track.id)
                                self.media_event_timer(track.time)
                        else:
                            self.send_private_msg('Failed to retrieve a result from last.fm.', self.user.nick)
                    else:
                        self.send_private_msg('No more than 50 tunes.', self.user.nick)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def search_lastfm_by_tag(self, search_str):
        """
        Searches last.fm for tunes matching the search term and creates a playlist from them.
        :param search_str: str the search term to search for.
        """
        if self.user.has_power or self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(search_str) is 0:
                self.send_private_msg('Missing search tag.', self.user.nick)
            else:
                self.send_private_msg('Please wait while creating playlist..', self.user.nick)
                last = lastfm.search_lastfm_by_tag(search_str)
                if last is not None:
                    if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                        self.media_manager.add_track_list(self.user.nick, last)
                        self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm*', self.user.nick)
                    else:
                        self.media_manager.add_track_list(self.user.nick, last)
                        self.send_private_msg('*Added:* ' + str(len(last)) + ' *tunes from last.fm*', self.user.nick)
                        track = self.media_manager.get_next_track()
                        self.send_media_broadcast_start(track.type, track.id)
                        self.media_event_timer(track.time)
                else:
                    self.send_private_msg('Failed to retrieve a result from last.fm.', self.user.nick)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_close_broadcast(self, user_name):
        """
        Close a user broadcasting.
        :param user_name: str the username to close.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.user.nick)
            else:
                user = self.find_user_info(user_name)
                if user is not None:
                    self.send_close_user_msg(user_name)
                else:
                    self.send_private_msg('No user named: ' + user_name, self.user.nick)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_clear(self):
        """ Clears the chat box. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            for x in range(0, 8):
                self.send_owner_run_msg(' ')
            else:
                clear = '133,133,133,133,133,133,133,133,133,133,133,133,133'
                self._send_command('privmsg', [clear, u'#262626,en'])
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_skip(self):
        """ Play the next item in the playlist. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if self.media_manager.is_last_track():
                self.send_bot_msg('*This is the last tune in the playlist.*', self.user.nick)
                self.send_private_msg('*This is the last tune in the playlist.*', self.user.nick)
            elif self.media_manager.is_last_track() is None:
                self.send_bot_msg('*No tunes to skip. The playlist is empty.*', self.user.nick)
                self.send_private_msg('*No tunes to skip. The playlist is empty.*', self.user.nick)
            else:
                self.cancel_media_event_timer()
                track = self.media_manager.get_next_track()
                self.send_media_broadcast_start(track.type, track.id)
                self.media_event_timer(track.time)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_delete_playlist_item(self, to_delete):
        """
        Delete item(s) from the playlist by index.
        :param to_delete: str index(es) to delete.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(self.media_manager.track_list) is 0:
                self.send_private_msg('The track list is empty.', self.user.nick)
            elif len(to_delete) is 0:
                self.send_private_msg('No indexes to delete provided.', self.user.nick)
            else:
                indexes = None
                by_range = False
                try:
                    if ':' in to_delete:
                        range_indexes = map(int, to_delete.split(':'))
                        temp_indexes = range(range_indexes[0], range_indexes[1] + 1)
                        if len(temp_indexes) > 1:
                            by_range = True
                    else:
                        temp_indexes = map(int, to_delete.split(','))
                except ValueError:
                    self.send_private_msg(self.user.nick, 'Wrong format.(ValueError)')
                else:
                    indexes = []
                    for i in temp_indexes:
                        if i < len(self.media_manager.track_list) and i not in indexes:
                            indexes.append(i)
                if indexes is not None and len(indexes) > 0:
                    result = self.media_manager.delete_by_index(indexes, by_range)
                    if result is not None:
                        if by_range:
                            self.send_private_msg('*Deleted from index:* %s *to index:* %s' % (result['from'],
                                                                                               result['to']),
                                                  self.user.nick)
                        elif result['deleted_indexes_len'] is 1:
                            self.send_private_msg('*Deleted* %s' % result['track_title'], self.user.nick)
                        else:
                            self.send_private_msg(
                                '*Deleted tracks at index:* %s' % ', '.join(result['deleted_indexes']),
                                self.user.nick)
                    else:
                        self.send_private_msg('Nothing was deleted.', self.user.nick)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_media_replay(self):
        """ Replays the last played media."""
        if self.media_manager.track() is not None:
            self.cancel_media_event_timer()
            self.send_media_broadcast_start(self.media_manager.track().type,
                                            self.media_manager.track().id)
            self.media_event_timer(self.media_manager.track().time)

    def do_play_media(self):
        """ Resumes a track in pause mode. """
        track = self.media_manager.track()
        if track is not None:
            if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                self.cancel_media_event_timer()
            if self.media_manager.is_paused:
                ntp = self.media_manager.mb_play(self.media_manager.elapsed_track_time())
                self.send_media_broadcast_play(track.type, self.media_manager.elapsed_track_time())
                self.media_event_timer(ntp)

    def do_media_pause(self):
        """ Pause the media playing. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            track = self.media_manager.track()
            if track is not None:
                if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                    self.cancel_media_event_timer()
                self.media_manager.mb_pause()
                self.send_media_broadcast_pause(track.type)

    def do_close_media(self):
        """ Closes the active media broadcast."""
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                self.cancel_media_event_timer()
            self.media_manager.mb_close()
            self.send_media_broadcast_close(self.media_manager.track().type)

    def do_clear_playlist(self):
        """ Clear the playlist. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(self.media_manager.track_list) > 0:
                pl_length = str(len(self.media_manager.track_list))
                self.media_manager.clear_track_list()
                self.send_private_msg('*Deleted* ' + pl_length + ' *items in the playlist.*', self.user.nick)
            else:
                self.send_private_msg('*The playlist is empty, nothing to delete.*', self.user.nick)

    def do_topic(self, topic):
        """
        Sets the room topic.
        :param topic: str the new topic.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(topic) is 0:
                self.send_topic_msg('')
                self.send_private_msg('Topic was cleared.', self.user.nick)
            else:
                self.send_topic_msg(topic)
                self.send_private_msg('The room topic was set to: ' + topic, self.user.nick)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_kick(self, user_name):
        """
        Kick a user out of the room.
        :param user_name: str the username to kick.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.user.nick)
            elif user_name == self.client_nick:
                self.send_private_msg('Action not allowed.', self.user.nick)
            else:
                user = self.find_user_info(user_name)
                if user is None:
                    self.send_private_msg('No user named: *' + user_name + '*', self.user.nick)
                elif user.is_owner or user.is_super:
                    self.send_private_msg('Not allowed.', self.user.nick)
                else:
                    self.send_ban_msg(user_name, user.id)
                    self.send_forgive_msg(user.id)
        else:
            self.send_private_msg('Command is not enabled for normal users.', self.user.nick)

    def do_ban(self, user_name):
        """
        Ban a user from the room.
        :param user_name: str the username to ban.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.user.nick)
            else:
                user = self.find_user_info(user_name)
                if user is None:
                    self.send_private_msg('No user named: *' + user_name + '*', self.user.nick)
                elif user.is_mod or user.is_owner or user.is_super:
                    self.send_private_msg('You cannot ban yourself or another moderator! Duh', self.user.nick)
                else:
                    self.send_ban_msg(user_name, user.id)

    def do_bad_nick(self, bad_nick):
        """
        Adds a bad username to the bad nicks file.
        :param bad_nick: str the bad nick to write to file.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(bad_nick) is 0:
                self.send_private_msg('Missing username.', self.user.nick)
            else:
                badnicks = pinylib.fh.file_reader(self.config_path(), CONFIG['nick_bans'])
                if badnicks is None:
                    pinylib.fh.file_writer(self.config_path(), CONFIG['nick_bans'], bad_nick)
                else:
                    if bad_nick in badnicks:
                        self.send_private_msg(bad_nick + ' is already in list.', self.user.nick)
                    else:
                        pinylib.fh.file_writer(self.config_path(), CONFIG['nick_bans'], bad_nick)
                        self.send_private_msg('*' + bad_nick + '* was added to file.', self.user.nick)

    def do_remove_bad_nick(self, bad_nick):
        """
        Removes a bad nick from bad nicks file.
        :param bad_nick: str the bad nick to remove from file.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(bad_nick) is 0:
                self.send_private_msg('Missing username', self.user.nick)
            else:
                rem = pinylib.fh.remove_from_file(self.config_path(), CONFIG['nick_bans'], bad_nick)
                if rem:
                    self.send_private_msg(bad_nick + ' was removed.', self.user.nick)

    def do_bad_account(self, bad_account_name):
        """
        Adds a bad account name to the bad accounts file.
        :param bad_account_name: str the bad account name to add to file.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(bad_account_name) is 0:
                self.send_private_msg('Account cannot be blank.', self.user.nick)
            elif len(bad_account_name) < 3:
                self.send_private_msg('Account to short: ' + str(len(bad_account_name)), self.user.nick)
            else:
                bad_accounts = pinylib.fh.file_reader(self.config_path(), CONFIG['account_bans'])
                if bad_accounts is None:
                    pinylib.fh.file_writer(self.config_path(), CONFIG['account_bans'], bad_account_name)
                else:
                    if bad_account_name in bad_accounts:
                        self.send_private_msg(bad_account_name + ' is already in list.', self.user.nick)
                    else:
                        pinylib.fh.file_writer(self.config_path(), CONFIG['account_bans'], bad_account_name)
                        self.send_private_msg('*' + bad_account_name + '* was added to file.', self.user.nick)

    def do_remove_bad_account(self, bad_account):
        """
        Removes a bad account from the bad accounts file.
        :param bad_account: str the bad account name to remove from file.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(bad_account) is 0:
                self.send_private_msg('Missing account.', self.user.nick)
            else:
                rem = pinylib.fh.remove_from_file(self.config_path(), CONFIG['account_bans'], bad_account)
                if rem:
                    self.send_private_msg(bad_account + ' was removed.', self.user.nick)

    def do_bad_string(self, bad_string):
        """
        Adds a bad string to the bad strings file.
        :param bad_string: str the bad string to add to file.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(bad_string) is 0:
                self.send_private_msg('Bad word cannot be blank.', self.user.nick)
            elif len(bad_string) < 3:
                self.send_private_msg('Bad word is to short: ' + str(len(bad_string)), self.user.nick)
            else:
                bad_strings = pinylib.fh.file_reader(self.config_path(), CONFIG['ban_strings'])
                if bad_strings is None:
                    pinylib.fh.file_writer(self.config_path(), CONFIG['ban_strings'], bad_string)
                else:
                    if bad_string in bad_strings:
                        self.send_private_msg(bad_string + ' is already in list.', self.user.nick)
                    else:
                        pinylib.fh.file_writer(self.config_path(), CONFIG['ban_strings'], bad_string)
                        self.send_private_msg('*' + bad_string + '* was added to file.', self.user.nick)

    def do_remove_bad_string(self, bad_string):
        """
        Removes a bad string from the bad strings file.
        :param bad_string: str the bad string to remove from file.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(bad_string) is 0:
                self.send_private_msg('Missing word.', self.user.nick)
            else:
                rem = pinylib.fh.remove_from_file(self.config_path(), CONFIG['ban_strings'], bad_string)
                if rem:
                    self.send_private_msg(bad_string + ' was removed.', self.user.nick)

    def do_list_info(self, list_type):
        """
        Shows info of different lists/files.
        :param list_type: str the type of list to find info for.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(list_type) is 0:
                self.send_private_msg('Missing list type.', self.user.nick)
            else:
                if list_type.lower() == 'nicks':
                    bad_nicks = pinylib.fh.file_reader(self.config_path(), CONFIG['nick_bans'])
                    if bad_nicks is None:
                        self.send_private_msg('*No items in this list.*', self.user.nick)
                    else:
                        self.send_private_msg(str(len(bad_nicks)) + ' bad nicks in list.', self.user.nick)
                elif list_type.lower() == 'words':
                    bad_strings = pinylib.fh.file_reader(self.config_path(), CONFIG['ban_strings'])
                    if bad_strings is None:
                        self.send_private_msg('No items in this list.', self.user.nick)
                    else:
                        self.send_private_msg(str(len(bad_strings)) + ' bad words in the list.', self.user.nick)
                elif list_type.lower() == 'accounts':
                    bad_accounts = pinylib.fh.file_reader(self.config_path(), CONFIG['account_bans'])
                    if bad_accounts is None:
                        self.send_private_msg('*No items in this list.*', self.user.nick)
                    else:
                        self.send_private_msg(str(len(bad_accounts)) + ' bad accounts in list.', self.user.nick)
                elif list_type.lower() == 'playlist':
                    if len(self.media_manager.track_list) > 0:
                        tracks = self.media_manager.get_track_list()
                        if tracks is not None:
                            i = 0
                            for pos, track in tracks:
                                if i == 0:
                                    self.send_owner_run_msg('(%s) *Next track: %s* %s' %
                                                            (pos, track.title, self.format_time(track.time)))
                                else:
                                    self.send_owner_run_msg('(%s) *%s* %s' %
                                                            (pos, track.title, self.format_time(track.time)))
                                i += 1
                elif list_type.lower() == 'mods':
                    if self.user.is_mod or self.user.is_owner or self.user.is_super:
                        if len(self.privacy_settings.room_moderators) is 0:
                            self.send_private_msg('*There is currently no moderators for this room.*', self.user.nick)
                        elif len(self.privacy_settings.room_moderators) is not 0:
                            mods = ', '.join(self.privacy_settings.room_moderators)
                            self.send_private_msg('*Moderators:* ' + mods, self.user.nick)

    def do_user_info(self, user_name):
        """
        Shows user object info for a given user name.
        :param user_name: str the user name of the user to show the info for.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.user.nick)
            else:
                user = self.find_user_info(user_name)
                if user is None:
                    self.send_private_msg('No user named: ' + user_name, self.user.nick)
                else:
                    self.send_private_msg('*ID:* ' + str(user.id), self.user.nick)
                    self.send_private_msg('*Is Mod:* ' + str(user.is_mod), self.user.nick)
                    self.send_private_msg('*Bot Control:* ' + str(user.has_power), self.user.nick)
                    self.send_private_msg('*Owner:* ' + str(user.is_owner), self.user.nick)
                    self.send_private_msg('*Account:* ' + str(user.user_account), self.user.nick)
                    self.send_private_msg('*Tinychat ID:* ' + str(user.tinychat_id), self.user.nick)
                    self.send_private_msg('*Last login:* ' + str(user.last_login), self.user.nick)
                    self.send_private_msg('*Last message:* ' + str(user.last_msg), self.user.nick)
        else:
            self.send_private_msg('*Command is not enabled for normal users.*', self.user.nick)

    def do_youtube_search(self, search_str):
        """
        Searches youtube for a given search term, and adds the results to a list.
        :param search_str: str the search term to search for.
        """
        if self.user.has_power or self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(search_str) is 0:
                self.send_private_msg('Missing search term.', self.user.nick)
            else:
                self.search_list = youtube.youtube_search_list(search_str, results=5)
                if len(self.search_list) is not 0:
                    for i in range(0, len(self.search_list)):
                        v_time = self.format_time(self.search_list[i]['video_time'])
                        v_title = self.search_list[i]['video_title']
                        self.send_owner_run_msg('(%s) *%s* %s' % (i, v_title, v_time))
                else:
                    self.send_private_msg('Could not find: ' + search_str, self.user.nick)
        else:
            self.send_private_msg('*Command is not enabled for normal users.*', self.user.nick)

    def do_play_youtube_search(self, int_choice):
        """
        Plays a youtube from the search list.
        :param int_choice: int the index in the search list to play.
        """
        if self.user.has_power or self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(self.search_list) > 1:
                try:
                    index_choice = int(int_choice)
                    if 0 <= index_choice <= 5:
                        if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                            track = self.media_manager.add_track(self.user.nick, self.search_list[index_choice])
                            self.send_bot_msg('(' + str(self.media_manager.last_track_index()) + ') *' +
                                              track.title + '* ' + track.time, self.user.nick)
                        else:
                            track = self.media_manager.mb_start(self.user.nick,
                                                                self.search_list[index_choice], mod_play=False)
                            self.send_media_broadcast_start(track.type, track.id)
                            self.media_event_timer(track.time)
                    else:
                        self.send_private_msg('Please make a choice between 1-5', self.user.nick)
                except ValueError:
                    self.send_private_msg('Only numbers allowed.', self.user.nick)
        else:
            self.send_private_msg('*Command is not enabled for normal users.*', self.user.nick)

    def do_cam_approve(self):
        """ Send a cam approve message to a user. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if self._b_password is None:
                conf = pinylib.tinychat.get_roomconfig_xml(self._roomname, self.room_pass, proxy=self._proxy)
                self._b_password = conf['bpassword']
                self._greenroom = conf['greenroom']
            if self._greenroom:
                self.send_cam_approve_msg(self.user.id, self.user.nick)

    # == Public Command Methods. ==
    def do_fullscreen(self):
        """ Posts a link to fullscreen chat with no adverts! """
        self.send_bot_msg('http://www.ruddernation.info/' + self._roomname, self.user.nick)

    def do_who_plays(self):
        """ shows who is playing the track. """
        if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
            track = self.media_manager.track()
            ago = self.format_time(int(pinylib.time.time() - track.rq_time) * 1000)
            self.send_bot_msg('*' + track.nick + '* requested this track: ' + ago + ' ago.', self.user.nick)
        else:
            self.send_bot_msg('*No track playing.*', self.user.nick)

    def do_help(self):
        """ Posts a link to github readme/wiki or other page about the bot commands. """
        self.send_bot_msg('*Commands:* https://github.com/TinyChat/Tinychat-Bot/wiki/', self.user.nick)

    def do_uptime(self):
        """ Shows the bots uptime. """
        self.send_bot_msg('*Uptime:* ' + self.format_time(self.get_runtime()), self.user.nick)

    def do_pmme(self):
        """ Opens a PM session with the bot. """
        self.send_private_msg('How can I help you *' + self.user.nick + '*?', self.user.nick)

    #  == Media Related Command Methods. ==
    def do_playlist_status(self):
        """ Shows info about the playlist. """
        if len(self.media_manager.track_list) is 0:
            self.send_bot_msg('*The playlist is empty.*')
        else:
            inquee = self.media_manager.queue()
            if inquee is not None:
                self.send_bot_msg(str(inquee[0]) + ' *items in the playlist.* ' +
                                  str(inquee[1]) + ' *Still in queue.*')
            else:
                self.send_bot_msg('Not enabled right now..')

    def do_next_tune_in_playlist(self):
        """ Shows next item in the playlist. """
        if self.media_manager.is_last_track():
            self.send_bot_msg('*This is the last track in the playlist.*', self.user.nick)
        elif self.media_manager.is_last_track() is None:
            self.send_bot_msg('*No tracks in the playlist.*', self.user.nick)
        else:
            pos, next_track = self.media_manager.next_track_info()
            if next_track is not None:
                self.send_bot_msg('(' + str(pos) + ') *' + next_track.title + '* ' +
                                  self.format_time(next_track.time), self.user.nick)
            else:
                self.send_bot_msg('Not enabled right now.', self.user.nick)

    def do_now_playing(self):
        """ Shows the currently playing media title. """
        if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
            track = self.media_manager.track()
            if len(self.media_manager.track_list) > 0:
                self.send_bot_msg('(' + str(self.media_manager.current_track_index()) + ')* ' +
                                  track.title + '* ' + self.format_time(track.time))
            else:
                self.send_bot_msg('*' + track.title + '* ' + self.format_time(track.time))
        else:
            self.send_bot_msg('*No track playing.*')

    def do_play_youtube(self, search_str):
        """ Plays a youtube video matching the search term, Example: play Lily Allen - The Fear(Explicit). """
        log.info('User: %s:%s is searching youtube: %s' % (self.user.nick, self.user.id, search_str))
        if self._is_client_mod or self._is_client_owner:
            if len(search_str) is 0:
                self.send_bot_msg('Please specify youtube title, id or link.')
            else:
                _youtube = youtube.youtube_search(search_str)
                if _youtube is None:
                    log.warning('Youtube request returned: %s' % _youtube)
                    self.send_bot_msg('Could not find video: ' + search_str)
                else:
                    log.info('Youtube found: %s' % _youtube)
                    if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                        track = self.media_manager.add_track(self.user.nick, _youtube)
                        self.send_bot_msg('(' + str(self.media_manager.last_track_index()) + ') *' +
                                          track.title + '* ' + self.format_time(track.time))
                    else:
                        track = self.media_manager.mb_start(self.user.nick, _youtube, mod_play=False)
                        self.send_media_broadcast_start(track.type, track.id)
                        self.media_event_timer(track.time)
        else:
            self.send_bot_msg('Not enabled right now.')

    def do_play_soundcloud(self, search_str):
        """ Plays a soundcloud matching the search term, Example: playsc woman screaming. """
        if self._is_client_mod or self._is_client_owner:
            if len(search_str) is 0:
                self.send_bot_msg('Please specify soundcloud title or id.')
            else:
                _soundcloud = soundcloud.soundcloud_search(search_str)
                if _soundcloud is None:
                    self.send_bot_msg('Could not find soundcloud: ' + search_str)
                else:
                    if self.media_timer_thread is not None and self.media_timer_thread.is_alive():
                        track = self.media_manager.add_track(self.user.nick, _soundcloud)
                        self.send_bot_msg('(' + str(self.media_manager.last_track_index()) + ') *' + track.title +
                                          '* ' + self.format_time(track.time))
                    else:
                        track = self.media_manager.mb_start(self.user.nick, _soundcloud, mod_play=False)
                        self.send_media_broadcast_start(track.type, track.id)
                        self.media_event_timer(track.time)
        else:
            self.send_bot_msg('Not enabled right now.')

    # Extra Features.
    def do_spy(self, roomname):
        """ Shows info for a selected Tinychat room and gives stats (Mods/user/cams), Example: spy ruddernation. """
        if len(roomname) is 0:
            self.send_bot_msg('*Missing room name.*')
        else:
            spy_info = pinylib.tinychat.spy_info(roomname)
            if spy_info is None:
                self.send_bot_msg('*The room is empty.*')
            elif spy_info == 'PW':
                self.send_bot_msg('*The room has a password on it!*')
            else:
                self.send_bot_msg('*Room:* ' + '*' + roomname + '*')
                self.send_bot_msg('*Moderators:* ' + spy_info['mod_count'])
                self.send_bot_msg('*Broadcasters:* ' + spy_info['broadcaster_count'])
                self.send_bot_msg('*Chatters:* ' + spy_info['total_count'])
                users = ', '.join(spy_info['users'])
                self.send_bot_msg('*Users: ' + users + '*')

    def do_account_spy(self, account):
        """ Shows info for a tinychat account if it exists, Example: spyuser ruddernation. """
        if len(account) is 0:
            self.send_bot_msg('*Missing username to search for.*')
        else:
            tc_usr = pinylib.tinychat.tinychat_user_info(account)
            if tc_usr is None:
                self.send_bot_msg('*Could not find tinychat info for:* ' + account)
            else:
                self.send_bot_msg('*Account:* ' + '*' + account + '*')
                self.send_bot_msg('*Website:* ' + tc_usr['website'])
                self.send_bot_msg('*Bio:* ' + tc_usr['biography'])
                self.send_bot_msg('*Last login:* ' + tc_usr['last_active'])

    def do_search_urban_dictionary(self, search_str):
        """ Shows urbandictionary's definition of search string, Example: urban wanker. """
        if self._is_client_mod or self._is_client_owner:
            if len(search_str) is 0:
                self.send_bot_msg('Please specify something to look up.', self.user.nick)
            else:
                urban = other.urbandictionary_search(search_str)
                if urban is None:
                    self.send_bot_msg('Could not find a definition for: ' + search_str, self.user.nick)
                else:
                    if len(urban) > 70:
                        chunks = string_utili.chunk_string(urban, 70)
                        for i in range(0, 2):
                            self.send_bot_msg(chunks[i])
                    else:
                        self.send_bot_msg(urban, self.user.nick)

    def do_weather_search(self, search_str):
        """ Shows weather info for a given location, Example: weather Copenhagen."""
        if len(search_str) is 0:
            self.send_bot_msg('Please specify a city to search for.', self.user.nick)
        else:
            weather = other.weather_search(search_str)
            if weather is None:
                self.send_bot_msg('Could not find weather data for: ' + search_str, self.user.nick)
            else:
                self.send_bot_msg(weather, self.user.nick)

    def do_whois_ip(self, ip_str):
        """ Shows whois info for a given ip address. """
        if len(ip_str) is 0:
            self.send_bot_msg('Please provide an IP address.', self.user.nick)
        else:
            whois = other.whois(ip_str)
            if whois is None:
                self.send_bot_msg('No info found for: ' + ip_str, self.user.nick)
            else:
                self.send_bot_msg(whois, self.user.nick)

    def do_time(self, location):
        """ Shows the time in a location using Time.is. """
        times = str(other.time_is(location))
        if len(location) is 0:
            self.send_bot_msg(' Please enter a location to fetch the time.', self.user.nick)
        else:
            if times is None:
                self.send_bot_msg(' We could not fetch the time in "' + str(location) + '".', self.user.nick)
            else:
                self.send_bot_msg('The time in *' + str(location) + '* is: *' + str(times) + "*", self.user.nick)

    def do_advice(self):
        """ Shows a random response from api.adviceslip.com """
        advised = other.advice()
        if advised is not None:
            self.send_bot_msg(advised, self.user.nick)

    def do_chuck_norris(self):
        """ Shows a chuck norris joke/quote. """
        chuck = other.chuck_norris()
        if chuck is not None:
            self.send_bot_msg(chuck, self.user.nick)

    def do_8ball(self, question):
        """
        Shows magic eight ball answer to a yes/no question.
        :param question: str the yes/no question.
        """
        if len(question) is 0:
            self.send_bot_msg('Use 8ball with a question, Example: 8ball am I going to win the lotto?')
        else:
            self.send_bot_msg('*8Ball* ' + locals.eight_ball())

    def do_translate(self, cmd_arg):
        if len(cmd_arg) is 0:
            self.send_bot_msg("Please enter a query to be translated to English, Example: translate jeg er fantastisk",
                              self.user.nick)
        else:
            translated_reply = other.translate(query=cmd_arg)
            self.send_bot_msg("In English: " + "*" + translated_reply + "*", self.user.nick)

    # Private Message commands for Mods/Super/Owner.
    def private_message_handler(self, msg_sender, private_msg):
        """
        Custom private message commands.
        :param msg_sender: str the user sending the private message.
        :param private_msg: str the private message.
        """
        if private_msg:
            pm_parts = private_msg.split(' ')
            pm_cmd = pm_parts[0].lower().strip()
            pm_arg = ' '.join(pm_parts[1:]).strip()

            # Super mod/owner commands.
            if pm_cmd == 'roompassword':
                threading.Thread(target=self.do_set_room_pass, args=(pm_arg,)).start()

            elif pm_cmd == 'campassword':
                threading.Thread(target=self.do_set_broadcast_pass, args=(pm_arg,)).start()

            elif pm_cmd == 'clearbans':
                threading.Thread(target=self.do_clear_room_bans).start()

            elif pm_cmd == 'green':
                threading.Thread(target=self.do_green_room).start()

            elif pm_cmd == 'mod':
                threading.Thread(target=self.do_make_mod, args=(pm_arg,)).start()

            elif pm_cmd == 'removemod':
                threading.Thread(target=self.do_remove_mod, args=(pm_arg,)).start()

            elif pm_cmd == 'directory':
                threading.Thread(target=self.do_directory).start()

            elif pm_cmd == 'p2t':
                threading.Thread(target=self.do_push2talk).start()

            elif pm_cmd == 'key':
                self.do_key(pm_arg)

            elif pm_cmd == 'nick':
                self.do_nick(pm_arg)

            elif pm_cmd == 'public':
                self.do_public_cmds()
            # Mod commands
            # User moderation settings.
            if pm_cmd == 'op':
                self.do_op_user(pm_parts)

            elif pm_cmd == 'deop':
                self.do_deop_user(pm_parts)

            elif pm_cmd == 'kick':
                self.do_kick(pm_arg)

            elif pm_cmd == 'ban':
                self.do_ban(pm_arg)

            elif pm_cmd == 'clearbn':
                self.do_clear_bad_nicks()

            elif pm_cmd == 'clearba':
                self.do_clear_bad_accounts()

            elif pm_cmd == 'guests':
                self.do_no_guest()

            elif pm_cmd == 'guestnicks':
                self.do_no_guest_nicks()

            elif pm_cmd == 'badnick':
                self.do_bad_nick(pm_arg)

            elif pm_cmd == 'removenick':
                self.do_remove_bad_nick(pm_arg)

            elif pm_cmd == 'badaccount':
                self.do_bad_account(pm_arg)

            elif pm_cmd == 'goodaccount':
                self.do_remove_bad_account(pm_arg)

            elif pm_cmd == 'badword':
                self.do_bad_string(pm_arg)

            elif pm_cmd == 'removeword':
                self.do_remove_bad_string(pm_arg)

            elif pm_cmd == 'clear':
                self.do_clear()
            # Misc settings.
            elif pm_cmd == 'topic':
                self.do_topic(pm_arg)

            elif pm_cmd == 'userinfo':
                self.do_user_info(pm_arg)

            elif pm_cmd == 'settings':
                self.do_room_settings()

            elif pm_cmd == 'list':
                threading.Thread(target=self.do_list_info, args=(pm_arg,)).start()

            # Video/Audio Settings.
            elif pm_cmd == 'up':
                self.do_cam_up(pm_arg)

            elif pm_cmd == 'down':
                self.do_cam_down(pm_arg)

            elif pm_cmd == 'cam':
                threading.Thread(target=self.do_cam_approve).start()

            elif pm_cmd == 'nocam':
                self.do_nocam(pm_arg)

            elif pm_cmd == 'close':
                self.do_close_broadcast(pm_arg)

            # Media Commands.
            # Bot Controller Commands
            elif pm_cmd == 'top':
                threading.Thread(target=self.do_lastfm_chart, args=(pm_cmd,)).start()

            elif pm_cmd == 'random':
                threading.Thread(target=self.do_lastfm_random_tunes, args=(pm_cmd,)).start()

            elif pm_cmd == 'tag':
                threading.Thread(target=self.search_lastfm_by_tag, args=(pm_cmd,)).start()

            elif pm_cmd == 'search':
                threading.Thread(target=self.do_youtube_search, args=(pm_arg,)).start()

            elif pm_cmd == 'psearch':
                self.do_play_youtube_search(pm_arg)
            # End of Bot Controller Commands
            elif pm_cmd == 'minfo':
                self.do_media_info()

            elif pm_cmd == 'pause':
                self.do_media_pause()

            elif pm_cmd == 'resume':
                self.do_play_media()

            elif pm_cmd == 'stop':
                self.do_close_media()

            elif pm_cmd == 'skip':
                self.do_skip()

            elif pm_cmd == 'replay':
                self.do_media_replay()

            elif pm_cmd == 'delete':
                self.do_delete_playlist_item(pm_arg)

            elif pm_cmd == 'clearpl':
                self.do_clear_playlist()

            # Public commands.
            if pm_cmd == 'super':
                self.do_super_user(pm_arg)

            elif pm_cmd == 'opme':
                self.do_opme(pm_arg)

            elif pm_cmd == 'pm':
                self.do_pm_bridge(pm_parts)

        # Print to console.
        self.console_write(pinylib.COLOR['white'], 'Private message from ' + msg_sender + ':' + str(private_msg)
                           .replace(self.key, '***KEY***')
                           .replace(CONFIG['super_key'], '***SUPER KEY***'))

    # == Super Mod Command Methods. ==
    def do_set_room_pass(self, password):
        """
        Set a room password for the room.
        :param password: str the room password
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if not password:
                self.privacy_settings.set_room_password()
                self.send_bot_msg('*The room password was removed.*')
                pinylib.time.sleep(1)
                self.send_private_msg('The room password was removed.', self.user.nick)
            elif len(password) > 1:
                self.privacy_settings.set_room_password(password)
                self.send_private_msg('*The room password is now:* ' + password, self.user.nick)
                pinylib.time.sleep(1)
                self.send_bot_msg('*The room is now password protected.*')
        else:
            self.send_bot_msg('Not available as the room owner account is not in the room.')

    def do_set_broadcast_pass(self, password):
        """
        Set a broadcast password for the room.
        :param password: str the password
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if not password:
                self.privacy_settings.set_broadcast_password()
                self.send_bot_msg('*The broadcast password was removed.*')
                pinylib.time.sleep(1)
                self.send_private_msg('The broadcast password was removed.', self.user.nick)
            elif len(password) > 1:
                self.privacy_settings.set_broadcast_password(password)
                self.send_private_msg('*The broadcast password is now:* ' + password, self.user.nick)
                pinylib.time.sleep(1)
                self.send_bot_msg('*Broadcast password is enabled.*')
        else:
            self.send_bot_msg('Not available as the room owner account is not in the room.')

    def do_key(self, new_key):
        """
        Shows or sets a new secret key.
        :param new_key: str the new secret key.
        """
        if self.user.is_owner or self.user.is_super:
            if len(new_key) is 0:
                self.send_private_msg('The current key is: *' + self.key + '*', self.user.nick)
            elif len(new_key) < 6:
                self.send_private_msg('Key must be at least 6 characters long: ' + str(len(self.key)),
                                      self.user.nick)
            elif len(new_key) >= 6:
                self.key = new_key
                self.send_private_msg('The key was changed to: *' + self.key + '*', self.user.nick)

    def do_clear_bad_nicks(self):
        """ Clears the bad nicks file. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            pinylib.fh.delete_file_content(self.config_path(), CONFIG['badnicks'])

    def do_clear_bad_strings(self):
        """ Clears the bad strings file. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            pinylib.fh.delete_file_content(self.config_path(), CONFIG['badstrings'])

    def do_clear_bad_accounts(self):
        """ Clears the bad accounts file. """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            pinylib.fh.delete_file_content(self.config_path(), CONFIG['badaccounts'])

    def do_op_user(self, msg_parts):
        """
        Lets moderators make a user a bot controller, This will also notify the user.
        :param msg_parts: list the pm message as a list.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(msg_parts) == 1:
                self.send_private_msg('Missing username.', self.user.nick)
            elif len(msg_parts) == 2:
                user = self.find_user_info(msg_parts[1])
                if user is not None:
                    user.has_power = True
                    self.send_private_msg(user.nick + ' is now a bot controller.', self.user.nick)
                    self.send_bot_msg(user.nick + ' is now a bot controller.', self.user.nick)
                    self.send_private_msg('You are now a bot controller.', user.nick)
                else:
                    self.send_private_msg('No user named: ' + msg_parts[1], self.user.nick)
        elif self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(msg_parts) == 1:
                self.send_private_msg('Missing username.', self.user.nick)
            elif len(msg_parts) == 2:
                self.send_private_msg('Missing key.', self.user.nick)
            elif len(msg_parts) == 3:
                if msg_parts[2] == self.key:
                    user = self.find_user_info(msg_parts[1])
                    if user is not None:
                        user.has_power = True
                        self.send_private_msg(user.nick + ' is now a bot controller.', self.user.nick)
                    else:
                        self.send_private_msg('No user named: ' + msg_parts[1], self.user.nick)
                else:
                    self.send_private_msg('Wrong key.', self.user.nick)
        else:
            self.send_private_msg('*This command is only available to Moderators.*', self.user.nick)

    def do_deop_user(self, msg_parts):
        """
        Lets the room owner, a mod or a bot controller remove a user from being a bot controller.
        NOTE: Mods or bot controllers will have to provide a key, owner and super does not.
        :param msg_parts: list the pm message as a list
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(msg_parts) == 1:
                self.send_private_msg('Missing username.', self.user.nick)
            elif len(msg_parts) == 2:
                user = self.find_user_info(msg_parts[1])
                if user is not None:
                    user.has_power = False
                    self.send_private_msg(user.nick + ' is not a bot controller anymore.', self.user.nick)
                else:
                    self.send_private_msg('No user named: ' + msg_parts[1], self.user.nick)
        elif self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(msg_parts) == 1:
                self.send_private_msg('Missing username.', self.user.nick)
            elif len(msg_parts) == 2:
                self.send_private_msg('Missing key.', self.user.nick)
            elif len(msg_parts) == 3:
                if msg_parts[2] == self.key:
                    user = self.find_user_info(msg_parts[1])
                    if user is not None:
                        user.has_power = False
                        self.send_private_msg(user.nick + ' is not a bot controller anymore.', self.user.nick)
                    else:
                        self.send_private_msg('No user named: ' + msg_parts[1], self.user.nick)
                else:
                    self.send_private_msg('Wrong key.', self.user.nick)
        else:
            self.send_private_msg('*This command is only available to Moderators.*', self.user.nick)

    def do_cam_up(self, key):
        """
        Makes the bot camup.
        NOTE: Mods or bot controllers will have to provide a key, owner and super does not.
        :param key str the key needed for moderators/bot controllers.
        """
        if self.user.is_owner or self.user.is_super:
            self.send_bauth_msg()
            self.send_create_stream()
            self.send_publish()
        elif self.user.is_mod or self.user.is_owner or self.user.is_super:
            if len(key) is 0:
                self.send_private_msg('Missing key.', self.user.nick)
            elif key == self.key:
                self.send_bauth_msg()
                self.send_create_stream()
                self.send_publish()
            else:
                self.send_private_msg('Wrong key.', self.user.nick)

    def do_cam_down(self, key):
        """
        Makes the bot cam down.
        NOTE: Mods or bot controllers will have to provide a key, owner and super does not.
        :param key: str the key needed for moderators/bot controllers.
        """
        if self.user.is_mod or self.user.is_owner or self.user.is_super:
            self.send_close_stream()
        elif self.user.is_owner or self.user.is_super:
            if len(key) is 0:
                self.send_private_msg('Missing key.', self.user.nick)
            elif key == self.key:
                self.send_close_stream()
            else:
                self.send_private_msg('Wrong key.', self.user.nick)

    def do_nocam(self, key):
        """
        Toggles if broadcasting is allowed or not.
        NOTE: Mods or bot controllers will have to provide a key, owner and super do not.
        :param key: str secret key.
        """
        if self.is_broadcasting_allowed or self.user.is_super:
            if self.user.is_owner:
                self.is_broadcasting_allowed = False
                self.send_private_msg('*Broadcasting is NOT allowed.*', self.user.nick)
            elif self.user.is_mod or self.user.is_owner or self.user.is_super:
                if len(key) is 0:
                    self.send_private_msg('missing key.', self.user.nick)
                elif key == self.key:
                    self.is_broadcasting_allowed = False
                    self.send_private_msg('*Broadcasting is NOT allowed.*', self.user.nick)
                else:
                    self.send_private_msg('Wrong key.', self.user.nick)
        else:
            if self.user.is_owner or self.user.is_super:
                self.is_broadcasting_allowed = True
                self.send_private_msg('*Broadcasting is allowed.*', self.user.nick)
            elif self.user.is_mod or self.user.is_owner or self.user.is_super:
                if len(key) is 0:
                    self.send_private_msg('missing key.', self.user.nick)
                elif key == self.key:
                    self.is_broadcasting_allowed = True
                    self.send_private_msg('*Broadcasting is allowed.*', self.user.nick)
                else:
                    self.send_private_msg('Wrong key.', self.user.nick)

    def do_no_guest(self):
        """ Toggles if guests are allowed to join the room or not. """
        if self.is_guest_entry_allowed:
            if self.user.is_mod or self.user.is_owner or self.user.is_super:
                self.is_guest_entry_allowed = False
                self.send_private_msg('*Guests are NOT allowed to join the room.*', self.user.nick)
                self.is_guest_entry_allowed = False
                self.send_private_msg('*Guests are NOT allowed to join.*', self.user.nick)
        else:
            if self.user.is_mod or self.user.is_owner or self.user.is_super:
                self.is_guest_entry_allowed = True
                self.send_private_msg('*Guests ARE allowed to join the room.*', self.user.nick)
                self.is_guest_entry_allowed = True
                self.send_private_msg('*Guests ARE allowed to join.*', self.user.nick)

    def do_no_guest_nicks(self):
        """ Toggles if guest nicks are allowed or not. """
        if self.user.is_mod or self.is_guest_nicks_allowed:
            if self.user.is_owner or self.user.is_super:
                self.is_guest_nicks_allowed = False
                self.send_private_msg('*Guest nicks are NOT allowed.*', self.user.nick)
                self.is_guest_nicks_allowed = False
                self.send_private_msg('*Guest nicks are NOT allowed.*', self.user.nick)
        else:
            if self.user.is_mod or self.user.is_owner or self.user.is_super:
                self.is_guest_nicks_allowed = True
                self.send_private_msg('*Guest nicks ARE allowed.*', self.user.nick)
                self.is_guest_nicks_allowed = True
                self.send_private_msg('*Guest nicks ARE allowed.*', self.user.nick)

    def do_public_cmds(self):
        """ Toggles if public commands are public or not, Super/Owner only command. """
        if self.is_cmds_public:
            if self.user.is_owner or self.user.is_super:
                self.is_cmds_public = False
                self.send_private_msg('*Public commands are disabled.*', self.user.nick)
                self.is_cmds_public = False
                self.send_private_msg('*Public commands are disabled.*', self.user.nick)
        else:
            if self.user.is_owner or self.user.is_super:
                self.is_cmds_public = True
                self.send_private_msg('*Public commands are enabled.*', self.user.nick)
                self.is_cmds_public = True
                self.send_private_msg('*Public commands are enabled.*', self.user.nick)

    # == Public PM Command Methods. ==
    def do_super_user(self, super_key):
        """
        Makes a user super mod, the highest level of mod.
        It is only possible to be a super mod if the client is owner.
        :param super_key: str the super key
        """
        if self._is_client_owner:
            if len(super_key) is 0:
                self.send_private_msg('Missing super key.', self.user.nick)
            elif super_key == CONFIG['super_key']:
                self.user.is_super = True
                self.send_private_msg('*You are now a super mod.*', self.user.nick)
            else:
                self.send_private_msg('Wrong super key.', self.user.nick)
        else:
            self.send_private_msg('Client is owner: *' + str(self._is_client_owner) + '*', self.user.nick)

    def do_opme(self, key):
        """
        Makes a user a bot controller if user provides the right key.
        :param key: str the secret key.
        """
        if len(key) is 0:
            self.send_private_msg('Missing key.', self.user.nick)
        elif key == self.key:
            self.user.has_power = True
            self.send_private_msg('You are now a bot controller.', self.user.nick)
            self.send_bot_msg('*' + self.user.nick + '*' + ' is now a bot controller.')
        else:
            self.send_private_msg('Wrong key.', self.user.nick)

    def do_pm_bridge(self, pm_parts):
        """
        Makes the bot work as a PM message bridge between 2 user who are not signed in.
        :param pm_parts: list the pm message as a list.
        """
        if len(pm_parts) == 1:
            self.send_private_msg('Missing username.', self.user.nick)
        elif len(pm_parts) == 2:
            self.send_private_msg('Use *pm username message*', self.user.nick)
        elif len(pm_parts) >= 3:
            pm_to = pm_parts[1]
            msg = ' '.join(pm_parts[2:])
            is_user = self.find_user_info(pm_to)
            if is_user is not None:
                if is_user.id == self._client_id:
                    self.send_private_msg('Action not allowed.', self.user.nick)
                else:
                    self.send_private_msg('*<' + self.user.nick + '>* ' + msg, pm_to)
            else:
                self.send_private_msg('No user named: ' + pm_to, self.user.nick)

    # Timed auto functions.
    def media_event_handler(self):
        """ This method gets called whenever a media is done playing. """
        if len(self.media_manager.track_list) > 0:
            if self.media_manager.is_last_track():
                if self.is_connected:
                    self.send_bot_msg('*Resetting playlist.*')
                self.media_manager.clear_track_list()
            else:
                track = self.media_manager.get_next_track()
                if track is not None and self.is_connected:
                    self.send_media_broadcast_start(track.type, track.id)
                self.media_event_timer(track.time)

    def media_event_timer(self, video_time):
        """
        Start a media event timer.
        :param video_time: int the time in milliseconds.
        """
        video_time_in_seconds = video_time / 1000
        self.media_timer_thread = threading.Timer(video_time_in_seconds, self.media_event_handler)
        self.media_timer_thread.start()

    def random_msg(self):
        """
        Pick a random message from a list of messages.
        :return: str random message.
        """
        upnext = 'Use *!play* youtube title/link/id to play youtube video or add to playlist.'
        plstat = 'Use *!playsc* soundcloud title/id to play soundcloud song or add to playlist.'
        if self.media_manager.is_last_track() is not None and not self.media_manager.is_last_track():
            pos, next_track = self.media_manager.next_track_info()
            if next_track is not None:
                next_video_time = self.format_time(next_track.time)
                upnext = '*Next is:* (' + str(pos) + ') *' + next_track.title + '* ' + next_video_time

        messages = [' :P ', ' ;) ', ' 8) ',
                    'I\'m not immature... I just know how to have fun!',
                    'Santa Claus has the right idea... visit people once a year.',
                    'Would a fly without wings be called a walk?',
                    'Unicorns are real. They\'re just fat and gray and we call them rhinos.',
                    upnext, plstat, '*I\'ve been online for*: ' + self.format_time(self.get_runtime()),
                    'For fullscreen use http://www.ruddernation.net/' + self._roomname]

        return random.choice(messages)

    def auto_msg_handler(self):
        """ The event handler for auto_msg_timer. """
        if self.is_connected:
            if CONFIG['auto_message_enabled']:
                self.send_bot_msg(self.random_msg(), use_chat_msg=True)
                self.connection.send_ping_request()
        self.start_auto_msg_timer()

    def start_auto_msg_timer(self):
        """
        In rooms with less activity, it can be useful to have the client send auto messages to keep the client alive.
        This method can be disabled by setting CONFIG['auto_message_enabled'] to False.
        The interval for when a message should be sent, is set with CONFIG['auto_message_interval']
        """
        threading.Timer(CONFIG['auto_message_interval'], self.auto_msg_handler).start()

    # Helper Methods.
    def get_privacy_settings(self):
        """ Parse the privacy settings page. """
        log.info('Parsing %s\'s privacy page. Proxy %s' % (self.account, self._proxy))
        self.privacy_settings = privacy_settings.TinychatPrivacyPage(self._proxy)
        self.privacy_settings.parse_privacy_settings()

    def config_path(self):
        """ Returns the path to the rooms configuration directory. """
        path = pinylib.SETTINGS['config_path'] + self._roomname + '/'
        return path

    def cancel_media_event_timer(self):
        """
        Cancel the media event timer if it is running.
        :return: True if canceled, else False
        """
        if self.media_timer_thread is not None:
            if self.media_timer_thread.is_alive():
                self.media_timer_thread.cancel()
                self.media_timer_thread = None
                return True
            return False
        return False

    @staticmethod
    def format_time(milliseconds):
        """
        Converts milliseconds or seconds to (day(s)) hours minutes seconds.
        :param milliseconds: int the milliseconds or seconds to convert.
        :return: str in the format (days) hh:mm:ss
        """
        m, s = divmod(milliseconds / 1000, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        if d == 0 and h == 0:
            human_time = '%02d Minutes and %02d seconds' % (m, s)
        elif d == 0:
            human_time = '%d hour(s) , %02d minutes and %02d seconds' % (h, m, s)
        else:
            human_time = '%d Day(s) %d:%02d:%02d' % (d, h, m, s)
        return human_time

    def check_msg_for_bad_string(self, msg):
        """
        Checks the chat message for bad string.
        :param msg: str the chat message.
        """
        msg_words = msg.split(' ')
        bad_strings = pinylib.fh.file_reader(self.config_path(), CONFIG['ban_strings'])
        if bad_strings is not None:
            for word in msg_words:
                if word in bad_strings:
                    self.send_ban_msg(self.user.nick, self.user.id)
                    self.send_forgive_msg(self.user.id)
                    self.send_bot_msg('*Auto-kicked*: (bad word!)')


def main():
    room_name = raw_input('Room Name: ')
    nickname = raw_input('Nick Name: (optional) ')
    room_password = getpass.getpass('Room Password: (optional) ')
    login_account = raw_input('Account: (optional)')
    login_password = getpass.getpass('Password: (optional)')

    client = TinychatBot(room_name, nick=nickname, account=login_account,
                         password=login_password, room_pass=room_password)

    t = threading.Thread(target=client.prepare_connect)
    t.daemon = True
    t.start()

    while not client.is_connected:
        pinylib.time.sleep(1)
    while client.is_connected:
        chat_msg = raw_input()
        if chat_msg.startswith('!'):
            cmd_parts = chat_msg.split(' ')
            cmd = cmd_parts[0].lower()
            if cmd == '/q':
                client.disconnect()
        else:
            client.send_bot_msg(chat_msg)


if __name__ == '__main__':
    if CONFIG['debug_to_file']:
        formater = '%(asctime)s : %(levelname)s : %(filename)s : %(lineno)d : %(funcName)s() : %(name)s : %(message)s'
        logging.basicConfig(filename=CONFIG['debug_file_name'], level=logging.DEBUG, format=formater)
        log.info('Starting bot_example.py version: %s, pinylib version: %s' %
                 (__version__, pinylib))
    else:
        log.addHandler(logging.NullHandler())
    main()
