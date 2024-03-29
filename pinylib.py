import time
import threading
import random
import traceback
import logging
import getpass
from colorama import init, Fore, Style
from apis import tinychat
from files import file_handler as fh
from rtmp import rtmp_protocol
from utilities import string_utili

__version__ = '5.0.0'

#  Basic settings.
SETTINGS = {
    'swf_version': '0675',                      # tinychat swf version.
    'chat_logging': True,                       # log chat messages/events.
    'debug_mode': False,                        # True shows additional info/errors.
    'debug_to_file': False,                     # log debug info to file.
    'console_colors': True,                     # use event based colors in the console.
    'enable_auto_job': True,                    # enable auto job(recommended).
    'use_24hour': True,                         # the console time format.
    'reset_time': False,                        # reset the run time after a reconnect.
    'reconnect_delay': 10,                      # initial reconnect delay in seconds.
    'auto_job_interval': 360,                   # auto job interval in seconds(360=6mins).
    'debug_file_name': 'pinylib_debug.log',     # debug log file name.
    'config_path': 'files/'                     # the path to the config folder.
}

#  Console colors.
COLOR = {
    'white': Fore.WHITE,
    'green': Fore.GREEN,
    'bright_green': Style.BRIGHT + Fore.GREEN,
    'yellow': Fore.YELLOW,
    'bright_yellow': Style.BRIGHT + Fore.YELLOW,
    'cyan': Fore.CYAN,
    'bright_cyan': Style.BRIGHT + Fore.CYAN,
    'red': Fore.RED,
    'bright_red': Style.BRIGHT + Fore.RED,
    'magenta': Fore.MAGENTA,
    'bright_magenta': Style.BRIGHT + Fore.MAGENTA
}

init(autoreset=True)
log = logging.getLogger(__name__)


def write_to_log(msg, room_name):
    """
    Writes chat events to log.
    The room name is used to construct a log file name from.
    :param msg: str the message to write to the log.
    :param room_name: str the room name.
    """
    d = time.strftime('%Y-%m-%d')
    file_name = d + '_' + room_name + '.log'
    path = SETTINGS['config_path'] + room_name + '/logs/'
    fh.file_writer(path, file_name, msg.encode(encoding='UTF-8', errors='ignore'))


class User:
    """
    A user object to hold info about a user.

    Each user will have a object associated with there username.
    The object is used to store information about the user.
    """
    def __init__(self, **kwargs):
        # Default's.
        self.lf = kwargs.get('lf', None)
        self.account = kwargs.get('account', '')
        self.is_owner = kwargs.get('own', False)
        self.gp = kwargs.get('gp', 0)
        self.alevel = kwargs.get('alevel', '')
        self.bf = kwargs.get('bf', False)
        self.nick = kwargs.get('nick', None)
        self.btype = kwargs.get('btype', '')
        self.id = kwargs.get('id', -1)
        self.stype = kwargs.get('stype', 0)
        self.is_mod = kwargs.get('mod', False)
        self.tinychat_id = None
        self.last_login = None
        # Extras.
        self.last_msg = None
        self.has_power = False
        self.is_super = False


class TinychatRTMPClient:
    """ Manages a single room connection to a given room. """
    def __init__(self, room, tcurl=None, app=None, room_type=None, nick=None, account='',
                 password=None, room_pass=None, ip=None, port=None, proxy=None):
        self.client_nick = nick
        self.account = account
        self.password = password
        self.room_pass = room_pass
        self.connection = None
        self.user = object
        self.is_connected = False
        self._roomname = room
        self._tc_url = tcurl
        self._app = app
        self._room_type = room_type
        self._ip = ip
        self._port = port
        self._proxy = proxy
        self._greenroom = False
        self._prefix = u'tinychat'
        self._swf_url = u'http://tinychat.com/embed/Tinychat-11.1-1.0.0.{0}.swf?version=1.0.0.{0}/[[DYNAMIC]]/8'\
            .format(SETTINGS['swf_version'])
        self._desktop_version = u'Desktop 1.0.0.%s' % SETTINGS['swf_version']
        self._embed_url = u'http://tinychat.com/' + self._roomname
        self._client_id = None
        self._bauth_key = None
        self._is_reconnected = False
        self._is_client_mod = False
        self._is_client_owner = False
        self._b_password = None
        self._room_users = {}
        self._reconnect_delay = SETTINGS['reconnect_delay']
        self._init_time = time.time()

    def console_write(self, color, message):
        """
        Writes message to console.
        :param color: the colorama color representation.
        :param message: str the message to write.
        """
        if SETTINGS['use_24hour']:
            ts = time.strftime('%H:%M:%S')
        else:
            ts = time.strftime('%I:%M:%S:%p')
        if SETTINGS['console_colors']:
            msg = COLOR['white'] + '[' + ts + '] ' + Style.RESET_ALL + color + message
        else:
            msg = '[' + ts + '] ' + message
        try:
            print(msg)
        except UnicodeEncodeError as ue:
            log.error(ue, exc_info=True)
            if SETTINGS['debug_mode']:
                traceback.print_exc()

        if SETTINGS['chat_logging']:
            write_to_log('[' + ts + '] ' + message, self._roomname)

    def prepare_connect(self):
        """ Gather necessary connection parameters before attempting to connect. """
        if self.account and self.password:
            log.info('Deleting old login cookies.')
            tinychat.delete_login_cookies()
            if len(self.account) > 3:
                log.info('Trying to log in with account: %s' % self.account)
                login = tinychat.post_login(self.account, self.password)
                if 'pass' in login['cookies']:
                    log.info('Logged in as: %s Cookies: %s' % (self.account, login['cookies']))
                    self.console_write(COLOR['green'], 'Logged in as: ' + login['cookies']['user'])
                else:
                    self.console_write(COLOR['red'], 'Log in Failed')
                    self.account = raw_input('Enter account: (optional)')
                    if self.account:
                        self.password = getpass.getpass('Enter password: ')
                    self.prepare_connect()
            else:
                self.console_write(COLOR['red'], 'Account name is to short.')
                self.account = raw_input('Enter account: ')
                self.password = getpass.getpass('Enter password: ')
                self.prepare_connect()

        config = tinychat.get_roomconfig_xml(self._roomname, self.room_pass, proxy=self._proxy)
        while config == 'PW':
            self.room_pass = getpass.getpass('The room is password protected. Enter room password: ')
            if not self.room_pass:
                self._roomname = raw_input('Enter room name: ')
                self.room_pass = getpass.getpass('Enter room pass: (optional)')
                self.account = raw_input('Enter account: (optional)')
                self.password = getpass.getpass('Enter password: (optional)')
                self.prepare_connect()
            else:
                config = tinychat.get_roomconfig_xml(self._roomname, self.room_pass, proxy=self._proxy)
                if config != 'PW':
                    break
                else:
                    self.console_write(COLOR['red'], 'Password Failed.')

        if SETTINGS['debug_mode']:
            for k in config:
                self.console_write(COLOR['white'], k + ': ' + str(config[k]))

        log.info('RTMP info found: %s' % config)
        self._ip = config['ip']
        self._port = config['port']
        self._tc_url = config['tcurl']
        self._app = config['app']
        self._room_type = config['roomtype']
        self._greenroom = config['greenroom']
        self._b_password = config['bpassword']

        self.console_write(COLOR['white'], '============ CONNECTING ============\n\n')
        self.connect()

    def connect(self):
        """ Attempts to make a RTMP connection with the given connection parameters. """
        if not self.is_connected:
            log.info('Trying to connect to: %s' % self._roomname)
            try:
                tinychat.recaptcha(proxy=self._proxy)
                cauth_cookie = tinychat.get_cauth_cookie(self._roomname, proxy=self._proxy)
                self.connection = rtmp_protocol.RtmpClient(self._ip, self._port, self._tc_url, self._embed_url,
                                                           self._swf_url, self._app, self._proxy)
                self.connection.connect(
                    {
                        'account': self.account,
                        'type': self._room_type,
                        'prefix': self._prefix,
                        'room': self._roomname,
                        'version': self._desktop_version,
                        'cookie': cauth_cookie
                    }
                )
                self.is_connected = True
                if SETTINGS['reset_time']:
                    self._init_time = time.time()
                self.__callback()
            except Exception as ex:
                log.error('Connect error: %s' % ex, exc_info=True)
                if SETTINGS['debug_mode']:
                    traceback.print_exc()
                self.reconnect()

    def disconnect(self):
        """ Closes the RTMP connection with the remote server. """
        log.info('Disconnecting from server.')
        try:
            self.is_connected = False
            self._is_client_mod = False
            self._bauth_key = None
            self._room_users.clear()
            self.connection.shutdown()
        except Exception as ex:
            log.error('Disconnect error: %s' % ex, exc_info=True)
            if SETTINGS['debug_mode']:
                traceback.print_exc()

    def reconnect(self):
        """ Reconnect to a room with the connection parameters already set. """
        reconnect_msg = '============ RECONNECTING IN ' + str(self._reconnect_delay) + ' SECONDS ============'
        log.info('Reconnecting: %s' % reconnect_msg)
        self.console_write(COLOR['bright_cyan'], reconnect_msg)
        self._is_reconnected = True
        self.disconnect()
        time.sleep(self._reconnect_delay)

        # increase reconnect_delay after each reconnect.
        self._reconnect_delay *= 2
        if self._reconnect_delay > 100:
            self._reconnect_delay = SETTINGS['reconnect_delay']

        if self.account and self.password:
            self.prepare_connect()
        else:
            self.connect()

    def __callback(self):
        """ Callback loop reading RTMP messages from the RTMP stream. """
        log.info('Starting the callback loop.')
        failures = 0
        amf0_data_type = -1
        amf0_data = None
        while self.is_connected:
            try:
                amf0_data = self.connection.reader.next()
                amf0_data_type = amf0_data['msg']
                if SETTINGS['debug_mode']:
                    self.console_write(COLOR['white'], str(amf0_data))
            except Exception as ex:
                failures += 1
                log.error('amf data read error count: %s %s' % (failures, ex), exc_info=True)
                if failures == 2:  # the amount of failures we allow before doing a reconnect.
                    if SETTINGS['debug_mode']:
                        traceback.print_exc()
                    self.reconnect()
                    break
            else:
                failures = 0
            try:
                handled = self.connection.handle_packet(amf0_data)
                if handled:
                    msg = 'Handled packet of type: %s Packet data: %s' % (amf0_data_type, amf0_data)
                    log.info(msg)
                    if SETTINGS['debug_mode']:
                        self.console_write(COLOR['white'], msg)
                    continue

                amf0_cmd = amf0_data['command']
                cmd = amf0_cmd[0]
                iparam0 = 0

                if cmd == '_result':
                    self.on_result(amf0_cmd)

                elif cmd == '_error':
                    self.on_error(amf0_cmd)

                elif cmd == 'onBWDone':
                    self.on_bwdone()

                elif cmd == 'onStatus':
                    self.on_status(amf0_cmd)

                elif cmd == 'registered':
                    client_info_dict = amf0_cmd[3]
                    self.on_registered(client_info_dict)

                elif cmd == 'join':
                    usr_join_info_dict = amf0_cmd[3]
                    threading.Thread(target=self.on_join, args=(usr_join_info_dict,)).start()

                elif cmd == 'joins':
                    current_room_users_info_list = amf0_cmd[3:]
                    if len(current_room_users_info_list) is not 0:
                        while iparam0 < len(current_room_users_info_list):
                            self.on_joins(current_room_users_info_list[iparam0])
                            iparam0 += 1

                elif cmd == 'joinsdone':
                    self.on_joinsdone()

                elif cmd == 'oper':
                    oper_id_name = amf0_cmd[3:]
                    while iparam0 < len(oper_id_name):
                        oper_id = str(oper_id_name[iparam0]).split('.0')
                        oper_name = oper_id_name[iparam0 + 1]
                        if len(oper_id) == 1:
                            self.on_oper(oper_id[0], oper_name)
                        iparam0 += 2

                elif cmd == 'deop':
                    deop_id = amf0_cmd[3]
                    deop_nick = amf0_cmd[4]
                    self.on_deop(deop_id, deop_nick)

                elif cmd == 'owner':
                    self.on_owner()

                elif cmd == 'avons':
                    avons_id_name = amf0_cmd[4:]
                    if len(avons_id_name) is not 0:
                        while iparam0 < len(avons_id_name):
                            avons_id = avons_id_name[iparam0]
                            avons_name = avons_id_name[iparam0 + 1]
                            self.on_avon(avons_id, avons_name)
                            iparam0 += 2

                elif cmd == 'pros':
                    pro_ids = amf0_cmd[4:]
                    if len(pro_ids) is not 0:
                        for pro_id in pro_ids:
                            pro_id = str(pro_id).replace('.0', '')
                            self.on_pro(pro_id)

                elif cmd == 'nick':
                    old_nick = amf0_cmd[3]
                    new_nick = amf0_cmd[4]
                    nick_id = int(amf0_cmd[5])
                    self.on_nick(old_nick, new_nick, nick_id)

                elif cmd == 'nickinuse':
                    self.on_nickinuse()

                elif cmd == 'quit':
                    quit_name = amf0_cmd[3]
                    quit_id = amf0_cmd[4]
                    self.on_quit(quit_id, quit_name)

                elif cmd == 'kick':
                    kick_id = amf0_cmd[3]
                    kick_name = amf0_cmd[4]
                    self.on_kick(kick_id, kick_name)

                elif cmd == 'banned':
                    self.on_banned()

                elif cmd == 'banlist':
                    banlist_id_nick = amf0_cmd[3:]
                    if len(banlist_id_nick) is not 0:
                        while iparam0 < len(banlist_id_nick):
                            banned_id = banlist_id_nick[iparam0]
                            banned_nick = banlist_id_nick[iparam0 + 1]
                            self.on_banlist(banned_id, banned_nick)
                            iparam0 += 2

                elif cmd == 'startbanlist':
                    # print(amf0_data)
                    pass

                elif cmd == 'topic':
                    topic = amf0_cmd[3]
                    self.on_topic(topic)

                elif cmd == 'from_owner':
                    owner_msg = amf0_cmd[3]
                    self.on_from_owner(owner_msg)

                elif cmd == 'doublesignon':
                    self.on_doublesignon()

                elif cmd == 'privmsg':
                    raw_msg = amf0_cmd[4]
                    msg_sender = amf0_cmd[6]
                    self.on_privmsg(msg_sender, raw_msg)

                elif cmd == 'notice':
                    notice_msg = amf0_cmd[3]
                    notice_msg_id = amf0_cmd[4]
                    if notice_msg == 'avon':
                        avon_name = amf0_cmd[5]
                        self.on_avon(notice_msg_id, avon_name)
                    elif notice_msg == 'pro':
                        self.on_pro(notice_msg_id)
                else:
                    self.console_write(COLOR['bright_red'], 'Unknown command: %s' % cmd)

            except Exception as ex:
                log.error('General callback error: %s' % ex, exc_info=True)
                if SETTINGS['debug_mode']:
                    traceback.print_exc()

    # Callback Event Methods.
    def on_result(self, result_info):
        if len(result_info) is 4 and type(result_info[3]) is int:
            stream_id = result_info[3]  # stream ID?
            log.debug('Stream ID: %s' % stream_id)
        if SETTINGS['debug_mode']:
            for list_item in result_info:
                if type(list_item) is rtmp_protocol.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['white'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['white'], str(list_item))

    def on_error(self, error_info):
        if SETTINGS['debug_mode']:
            for list_item in error_info:
                if type(list_item) is rtmp_protocol.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['bright_red'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['bright_red'], str(list_item))

    def on_status(self, status_info):
        if SETTINGS['debug_mode']:
            for list_item in status_info:
                if type(list_item) is rtmp_protocol.pyamf.ASObject:
                    for k in list_item:
                        self.console_write(COLOR['white'], k + ': ' + str(list_item[k]))
                else:
                    self.console_write(COLOR['white'], str(list_item))

    def on_bwdone(self):
        if not self._is_reconnected:
            if SETTINGS['enable_auto_job']:
                self.start_auto_job_timer()

    def on_registered(self, client_info):
        self._client_id = client_info['id']
        self._is_client_mod = client_info['mod']
        self._is_client_owner = client_info['own']
        self.add_user_info(client_info)

        self.console_write(COLOR['bright_green'], 'registered with ID: %d' % self._client_id)

        key = tinychat.get_captcha_key(self._roomname, str(self._client_id), proxy=self._proxy)
        if key is None:
            self.console_write(COLOR['bright_red'], 'There was a problem obtaining the captcha key. Key=%s' % str(key))
        else:
            self.console_write(COLOR['bright_green'], 'Captcha key: %s' % key)
            self.send_cauth_msg(key)
            self.set_nick()

    def on_join(self, join_info_dict):
        user = self.add_user_info(join_info_dict)

        if join_info_dict['account']:
            tc_info = tinychat.tinychat_user_info(join_info_dict['account'])
            if tc_info is not None:
                user.tinychat_id = tc_info['tinychat_id']
                user.last_login = tc_info['last_active']
            if join_info_dict['own']:
                self.console_write(COLOR['red'], 'Room Owner %s:%d:%s' %
                                   (join_info_dict['nick'], join_info_dict['id'], join_info_dict['account']))
            elif join_info_dict['mod']:
                self.console_write(COLOR['bright_red'], 'Moderator %s:%d:%s' %
                                   (join_info_dict['nick'], join_info_dict['id'], join_info_dict['account']))
            else:
                self.console_write(COLOR['bright_yellow'], '%s:%d has account: %s' %
                                   (join_info_dict['nick'], join_info_dict['id'], join_info_dict['account']))
        else:
            if join_info_dict['id'] is not self._client_id:
                self.console_write(COLOR['cyan'], '%s:%d joined the room.' %
                                   (join_info_dict['nick'], join_info_dict['id']))

    def on_joins(self, joins_info_dict):
        self.add_user_info(joins_info_dict)

        if joins_info_dict['account']:
            if joins_info_dict['own']:
                self.console_write(COLOR['red'], 'Joins Room Owner %s:%d:%s' %
                                   (joins_info_dict['nick'], joins_info_dict['id'], joins_info_dict['account']))
            elif joins_info_dict['mod']:
                self.console_write(COLOR['bright_red'], 'Joins Moderator %s:%d:%s' %
                                   (joins_info_dict['nick'], joins_info_dict['id'], joins_info_dict['account']))
            else:
                self.console_write(COLOR['bright_yellow'], 'Joins %s:%d:%s' %
                                   (joins_info_dict['nick'], joins_info_dict['id'], joins_info_dict['account']))
        else:
            if joins_info_dict['id'] is not self._client_id:
                self.console_write(COLOR['bright_cyan'], 'Joins %s:%d' %
                                   (joins_info_dict['nick'], joins_info_dict['id']))

    def on_joinsdone(self):
        if self._is_client_mod:
            self.send_banlist_msg()

    def on_oper(self, uid, nick):
        user = self.find_user_info(nick)
        user.is_mod = True
        if uid != self._client_id:
            self.console_write(COLOR['bright_red'], '%s:%s is moderator.' % (nick, uid))

    def on_deop(self, uid, nick):
        user = self.find_user_info(nick)
        user.is_mod = False
        self.console_write(COLOR['red'], '%s:%s was modded.' % (nick, uid))

    def on_owner(self):
        pass

    def on_avon(self, uid, name):
        self.console_write(COLOR['cyan'], '%s:%s is broadcasting.' % (name, uid))

    def on_pro(self, uid):
        self.console_write(COLOR['cyan'], '%s is pro.' % uid)

    def on_nick(self, old, new, uid):
        if uid != self._client_id:
            old_info = self.find_user_info(old)
            old_info.nick = new
            if old in self._room_users.keys():
                del self._room_users[old]
                self._room_users[new] = old_info
            self.console_write(COLOR['bright_cyan'], '%s:%s changed nick to: %s' % (old, uid, new))

    def on_nickinuse(self):
        self.client_nick += str(random.randint(0, 10))
        self.console_write(COLOR['white'], 'Nick already taken. Changing nick to: %s' % self.client_nick)
        self.set_nick()

    def on_quit(self, uid, name):
        if name in self._room_users.keys():
            del self._room_users[name]
            self.console_write(COLOR['cyan'], '%s:%s left the room.' % (name, uid))

    def on_kick(self, uid, name):
        self.console_write(COLOR['bright_red'], '%s:%s was banned.' % (name, uid))
        self.send_banlist_msg()

    def on_banned(self):
        self.console_write(COLOR['red'], 'You are banned from this room.')

    def on_banlist(self, uid, nick):
        self.console_write(COLOR['bright_red'], 'Banned user: %s:%s' % (nick, uid))

    def on_topic(self, topic):
        topic_msg = topic.encode('utf-8', 'replace')
        self.console_write(COLOR['cyan'], 'room topic: ' + topic_msg)

    def on_from_owner(self, owner_msg):
        msg = str(owner_msg).replace('notice', '').replace('%20', ' ')
        self.console_write(COLOR['bright_red'], msg)

    def on_doublesignon(self):
        self.console_write(COLOR['bright_red'], 'Double account sign on. Aborting!')
        self.is_connected = False

    def on_reported(self, uid, nick):
        self.console_write(COLOR['bright_red'], 'You were reported by: %s:%s' % (nick, uid))

    def on_privmsg(self, msg_sender, raw_msg):
        """
        Message command controller
        :param msg_sender: str the sender of the message.
        :param raw_msg: str the unencoded message.
        """

        # Get user info object of the user sending the message..
        self.user = self.find_user_info(msg_sender)

        # decode the message from comma separated decimal to normal text
        decoded_msg = self._decode_msg(u'' + raw_msg)

        if decoded_msg.startswith('/'):
            msg_cmd = decoded_msg.split(' ')
            if msg_cmd[0] == '/msg':
                private_msg = ' '.join(msg_cmd[2:])
                self.private_message_handler(msg_sender, private_msg.strip())

            elif msg_cmd[0] == '/reported':
                self.on_reported(self.user.id, msg_sender)

            elif msg_cmd[0] == '/mbs':
                if self.user.is_mod:
                    if len(msg_cmd) is 3:
                        media_type = msg_cmd[1]
                        media_id = msg_cmd[2]
                        threading.Thread(target=self.on_media_broadcast_start,
                                         args=(media_type, media_id, msg_sender, )).start()

            elif msg_cmd[0] == '/mbc':
                if self.user.is_mod:
                    if len(msg_cmd) is 2:
                        media_type = msg_cmd[1]
                        self.on_media_broadcast_close(media_type, msg_sender)

            elif msg_cmd[0] == '/mbpa':
                if self.user.is_mod:
                    if len(msg_cmd) is 2:
                        media_type = msg_cmd[1]
                        self.on_media_broadcast_paused(media_type, msg_sender)

            elif msg_cmd[0] == '/mbpl':
                if self.user.is_mod:
                    if len(msg_cmd) is 3:
                        media_type = msg_cmd[1]
                        time_point = int(msg_cmd[2])
                        self.on_media_broadcast_play(media_type, time_point, msg_sender)

            elif msg_cmd[0] == '/mbsk':
                if self.user.is_mod:
                    if len(msg_cmd) is 3:
                        media_type = msg_cmd[1]
                        time_point = int(msg_cmd[2])
                        self.on_media_broadcast_skip(media_type, time_point, msg_sender)
        else:
            self.message_handler(msg_sender, decoded_msg.strip())

    # Message Handler.
    def message_handler(self, msg_sender, decoded_msg):
        """
        Message handler.
        :param msg_sender: str the user sending a message.
        :param decoded_msg: str the decoded msg(text).
        """
        self.console_write(COLOR['green'], '%s: %s ' % (msg_sender, decoded_msg))

    # Private message Handler.
    def private_message_handler(self, msg_sender, private_msg):
        """
        A user private message us.
        :param msg_sender: str the user sending the private message.
        :param private_msg: str the private message.
        """
        self.console_write(COLOR['white'], 'Private message from %s: %s' % (msg_sender, private_msg))

    # Media Events.
    def on_media_broadcast_start(self, media_type, video_id, usr_nick):
        """
        A user started a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param video_id: str the youtube ID or soundcloud trackID.
        :param usr_nick: str the user name of the user playing media.
        """
        self.console_write(COLOR['bright_magenta'], '%s is playing %s %s' % (usr_nick, media_type, video_id))

    def on_media_broadcast_close(self, media_type, usr_nick):
        """
        A user closed a media broadcast.
        :param media_type: str the type of media. youTube or soundCloud.
        :param usr_nick: str the user name of the user closing the media.
        """
        self.console_write(COLOR['bright_magenta'], '%s closed the %s' % (usr_nick, media_type))

    def on_media_broadcast_paused(self, media_type, usr_nick):
        """
        A user paused the media broadcast.
        :param media_type: str the type of media being paused. youTube or soundCloud.
        :param usr_nick: str the user name of the user pausing the media.
        """
        self.console_write(COLOR['bright_magenta'], '%s paused the %s' % (usr_nick, media_type))

    def on_media_broadcast_play(self, media_type, time_point, usr_nick):
        """
        A user resumed playing a media broadcast.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user resuming the tune.
        """
        self.console_write(COLOR['bright_magenta'], '%s resumed the %s at: %s' %
                           (usr_nick, media_type, time_point))

    def on_media_broadcast_skip(self, media_type, time_point, usr_nick):
        """
        A user time searched a tune.
        :param media_type: str the media type. youTube or soundCloud.
        :param time_point: int the time point in the tune in milliseconds.
        :param usr_nick: str the user time searching the tune.
        """
        self.console_write(COLOR['bright_magenta'], '%s time searched the %s at: %s ' %
                           (usr_nick, media_type, time_point))

    # User Related
    def add_user_info(self, user_info):
        """
        Find the user object for a given user name and add to it.
        We use this method to add info to our user info object.
.
        :param user_info: dict the user info dictionary.
        :return: object a user object containing user info.
        """
        if user_info['nick'] not in self._room_users:
            self._room_users[user_info['nick']] = User(**user_info)
        return self._room_users[user_info['nick']]

    def find_user_info(self, usr_nick):
        """
        Find the user object for a given user name.
        Instead of adding to the user info object, we return None if the user name is NOT in the room_users dict.
        We use this method when we are getting user input to look up.

        :param usr_nick: str the user name to find info for.
        :return: object or None if no user name is in the room_users dict.
        """
        if usr_nick in self._room_users:
            return self._room_users[usr_nick]
        return None

    # Message Methods.
    def send_bauth_msg(self):
        """ Get and send the bauth key needed before we can start a broadcast. """
        if self._bauth_key is not None:
            self._send_command('bauth', [u'' + self._bauth_key])
        else:
            _token = tinychat.get_bauth_token(self._roomname, self.client_nick,
                                              self._client_id, self._greenroom, proxy=self._proxy)
            if _token != 'PW':
                self._bauth_key = _token
                self._send_command('bauth', [u'' + _token])

    def send_cauth_msg(self, cauthkey):
        """
        Send the cauth key message with a working cauth key, we need to send this before we can chat.
        :param cauthkey: str a working cauth key.
        """
        self._send_command('cauth', [u'' + cauthkey])

    def send_owner_run_msg(self, msg):
        """
        Send owner run message.
        :param msg: the message str to send.
        """
        if self._is_client_mod:
            self._send_command('owner_run', [u'notice' + msg.replace(' ', '%20')])

    def send_cam_approve_msg(self, nick, uid=None):  # NEW
        """
        Send cam approval message.
        NOTE: if no uid is provided, we try and look up the user by nick.
        :param nick: str the nick to be approved.
        :param uid: (optional) the user id.
        """
        if self._is_client_mod and self._b_password is not None:
            msg = '/allowbroadcast %s' % self._b_password
            if uid is None:
                user = self.find_user_info(nick)
                if user is not None:
                    self._send_command('privmsg', [u'' + self._encode_msg(msg), u'#0,en',
                                                   u'n' + str(user.uid) + '-' + nick])
            else:
                self._send_command('privmsg', [u'' + self._encode_msg(msg), u'#0,en', u'n' + str(uid) + '-' + nick])

    def send_chat_msg(self, msg):
        """
        Send a chat room message.
        :param msg: str the message to send.
        """
        self._send_command('privmsg', [u'' + self._encode_msg(msg), u'#262626,en'])

    def send_private_msg(self, msg, nick):
        """
        Send a private message.
        :param msg: str the private message to send.
        :param nick: str the user name to receive the message.
        """
        user = self.find_user_info(nick)
        if user is not None:
            self._send_command('privmsg', [u'' + self._encode_msg('/msg ' + nick + ' ' + msg),
                                           u'#262626,en', u'n' + str(user.id) + '-' + nick])
            self._send_command('privmsg', [u'' + self._encode_msg('/msg ' + nick + ' ' + msg),
                                           u'#262626,en', u'b' + str(user.id) + '-' + nick])

    def send_userinfo_request_msg(self, user_id):
        """
        Send user info request to a user.
        :param user_id: str user id of the user we want info from.
        """
        self._send_command('account', [u'' + str(user_id)])

    def send_undercover_msg(self, nick, msg):
        """
        Send a 'undercover' message.
        This is a special message that appears in the main chat, but is only visible to the user it is sent to.
        It can also be used to play 'private' youtubes/soundclouds with.

        :param nick: str the user name to send the message to.
        :param msg: str the message to send.
        """
        user = self.find_user_info(nick)
        if user is not None:
            self._send_command('privmsg', [u'' + self._encode_msg(msg), '#0,en', u'b' + str(user.id) + '-' + nick])
            self._send_command('privmsg', [u'' + self._encode_msg(msg), '#0,en', u'n' + str(user.id) + '-' + nick])

    def set_nick(self):
        """ Send the nick message. """
        if not self.client_nick:
            self.client_nick = string_utili.create_random_string(5, 25)
        self.console_write(COLOR['white'], 'Setting nick: %s' % self.client_nick)
        self._send_command('nick', [u'' + self.client_nick])

    def send_ban_msg(self, nick, uid=None):
        if self._is_client_mod:
            if uid is None:
                user = self.find_user_info(nick)
                if user is not None:
                    self._send_command('kick', [u'' + nick, str(user.id)])
            else:
                self._send_command('kick', [u'' + nick, str(uid)])

    def send_forgive_msg(self, uid):
        """
        Send forgive message.
        :param uid: The ID of the user we want to forgive.
        """
        if self._is_client_mod:
            self._send_command('forgive', [u'' + str(uid)])
            # get the updated ban list.
            self.send_banlist_msg()

    def send_banlist_msg(self):
        """ Send ban list message. """
        if self._is_client_mod:
            self._send_command('banlist')

    def send_topic_msg(self, topic):
        """
        Send a room topic message.
        :param topic: str the room topic.
        """
        if self._is_client_mod:
            self._send_command('topic', [u'' + topic])

    def send_close_user_msg(self, nick):
        """
        Send close user broadcast message.
        :param nick: str the user name of the user we want to close.
        """
        if self._is_client_mod:
            self._send_command('owner_run', [u'_close' + nick])

    def send_create_stream(self):
        """ Send createStream message. """
        self.console_write(COLOR['white'], 'Sending createStream message.')
        self._send_command('createStream')

    def send_close_stream(self):
        """ Send closeStream message. """
        self.console_write(COLOR['white'], 'Sending closeStream message.')
        self._send_command('closeStream')

    def send_deletestream(self):
        self.console_write(COLOR['white'], 'Sending deleteStream message.')
        self._send_command('deleteStream', [1])

    def send_play(self, user_id):
        self.console_write(COLOR['white'], 'Sending play message for stream: %d.' % user_id)
        self._send_command('play', [str(user_id)])

    def send_publish(self):
        """ Send publish message. """
        self.console_write(COLOR['white'], 'Sending publish message.')
        self._send_command('publish', [u'' + str(self._client_id), u'live'])

    # Media Message Functions
    def send_media_broadcast_start(self, media_type, video_id, time_point=0, private_nick=None):
        """
        Starts a media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param video_id: str the media video ID.
        :param time_point: int where to start the media from in milliseconds.
        :param private_nick: str if not None, start the media broadcast for this username only.
        """
        mbs_msg = '/mbs %s %s %s' % (media_type, video_id, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbs_msg)
        else:
            self.send_chat_msg(mbs_msg)

    def send_media_broadcast_close(self, media_type, private_nick=None):
        """
        Close a media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param private_nick str if not None, send this message to this username only.
        """
        mbc_msg = '/mbc %s' % media_type
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbc_msg)
        else:
            self.send_chat_msg(mbc_msg)

    def send_media_broadcast_play(self, media_type, time_point, private_nick=None):
        """
        Play a currently paused media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param time_point: int where to play the media from in milliseconds.
        :param private_nick: str if not None, send this message to this username only.
        """
        mbpl_msg = '/mbpl %s %s' % (media_type, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbpl_msg)
        else:
            self.send_chat_msg(mbpl_msg)

    def send_media_broadcast_pause(self, media_type, private_nick=None):
        """
        Pause a currently playing media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param private_nick: str if not None, send this message to this username only.
        """
        mbpa_msg = '/mbpa %s' % media_type
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbpa_msg)
        else:
            self.send_chat_msg(mbpa_msg)

    def send_media_broadcast_skip(self, media_type, time_point, private_nick=None):
        """
        Time search a currently playing/paused media broadcast.
        :param media_type: str 'youTube' or 'soundCloud'
        :param time_point: int the time point to skip to.
        :param private_nick: str if not None, send this message to this username only.
        :return:
        """
        mbsk_msg = '/mbsk %s %s' % (media_type, time_point)
        if private_nick is not None:
            self.send_undercover_msg(private_nick, mbsk_msg)
        else:
            self.send_chat_msg(mbsk_msg)

    # Message Construction.
    def _send_command(self, cmd, params=None, trans_id=0):
        """
        Sends command messages to the server.

        NOTE: Im not sure what kind of effect the trans ID has,
        or if it indeed is the transaction ID.

        :param cmd: str command name.
        :param params: list command parameters.
        :param trans_id: int the trans action ID.
        """
        msg_format = [u'' + cmd, trans_id, None]
        if params and type(params) is list:
            msg_format.extend(params)
        msg = {
            'msg': rtmp_protocol.types.DT_COMMAND,
            'command': msg_format
        }
        try:
            self.connection.writer.write(msg)
            self.connection.writer.flush()
        except Exception as ex:
            log.error('send command error: %s' % ex, exc_info=True)
            if SETTINGS['debug_mode']:
                traceback.print_exc()
            self.reconnect()

    # Helper Methods
    def get_runtime(self, milliseconds=True):
        """
        Get the time the connection has been alive.
        :param milliseconds: bool True return the time as milliseconds, False return seconds.
        :return: int milliseconds or seconds.
        """
        up = int(time.time() - self._init_time)
        if milliseconds:
            return up * 1000
        return up

    @staticmethod
    def _decode_msg(msg):
        """
        Decode str from comma separated decimal to normal text str.
        :param msg: str the encoded message.
        :return: str normal text.
        """
        chars = msg.split(',')
        msg = ''
        for i in chars:
            try:
                msg += unichr(int(i))
            except ValueError as ve:
                log.error('%s' % ve, exc_info=True)
        return msg

    @staticmethod
    def _encode_msg(msg):
        """
        Encode normal text str to comma separated decimal.
        :param msg: str the normal text to encode
        :return: comma separated decimal str.
        """
        return ','.join(str(ord(char)) for char in msg)

    # Timed Auto Method.
    def auto_job_handler(self):
        """ The event handler for auto_job_timer. """
        if self.is_connected:
            conf = tinychat.get_roomconfig_xml(self._roomname, self.room_pass, proxy=self._proxy)
            if conf is not None:
                if self._is_client_mod:
                    self._greenroom = conf['greenroom']
                    self._b_password = conf['bpassword']
            log.info('recv configuration: %s' % conf)
        self.start_auto_job_timer()

    def start_auto_job_timer(self):
        """
        Just like using tinychat with a browser, this method will
        fetch the room config from tinychat API every 4 minutes 30 seconds(270 seconds).
        See line 228 at https://tinychat.com/embed/chat.js
        """
        threading.Timer(SETTINGS['auto_job_interval'], self.auto_job_handler).start()


def main():
    room_name = raw_input('Room Name: ')
    nickname = raw_input('Nick Name: (optional) ')
    room_password = getpass.getpass('Room Password: (optional) ')
    login_account = raw_input('Account: (optional)')
    login_password = getpass.getpass('Password: (optional)')

    client = TinychatRTMPClient(room_name, nick=nickname, account=login_account,
                                password=login_password, room_pass=room_password)

    t = threading.Thread(target=client.prepare_connect)
    t.daemon = True
    t.start()
    while not client.is_connected:
        time.sleep(1)
    while client.is_connected:
        chat_msg = raw_input()
        if chat_msg.lower() == 'q':
            client.disconnect()
        else:
            client.send_chat_msg(chat_msg)

if __name__ == '__main__':
    if SETTINGS['debug_to_file']:
        formater = '%(asctime)s : %(levelname)s : %(filename)s : %(lineno)d : %(funcName)s() : %(name)s : %(message)s'
        logging.basicConfig(filename=SETTINGS['debug_file_name'], level=logging.DEBUG, format=formater)
        log.info('Starting pinylib version: %s' % __version__)
    else:
        log.addHandler(logging.NullHandler())
    main()
