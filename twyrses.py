#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# A curses based twitter client
#
# Requires:
#	urwid - http://excess.org/urwid/
# 	python-twitter - http://code.google.com/p/python-twitter/
#				http://static.unto.net/python-twitter/0.6/doc/twitter.html
#
# To do:
#	undo update status in n seconds
#   Paging for statuses when scrolled to the bottom of the page
#	User info persistence
#	auto complete for friend nicks
#	follow / unfollow twittard
#	Search
#	User info persistence
#	OAuth integration
#   	Send source parameter
#	View ASCII version of user's avatar
#	auto complete for friend nicks
#	delete tweet
#	Retweet autocompletion - type RT @twittard and up or down arrow
#		scrolls through available tweets
#   User stats
#	undo update status in n seconds
#   Paging for statuses when scrolled to the bottom of the page
#	help
#	i18n
#	clickable screen names

"""
A curses based twitter client

Usage:
twyrses.py [username]

"""

import sys, getpass, pickle
import datetime
from string import zfill
import urwid, urwid.curses_display, urwid.raw_display
from urllib2 import HTTPError

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except:
        print "No usable json library detected. Please either upgrade to python 2.6, or install simplejson"
        sys.exit()
    
import webbrowser

# Twitter library imports
import os
current_file_path = os.path.dirname(__file__)
sys.path.append(os.path.join(current_file_path, 'tweepy'))
import tweepy

#config file imports
from ConfigParser import *

import locale
locale.setlocale(locale.LC_ALL, '')
code = locale.getpreferredencoding()

utf8decode = urwid.escape.utf8decode

CHAR_LIMIT = 140
CHAR_LIMIT_MED = 120		
CHAR_LIMIT_LOW = 130
REFRESH_TIMEOUT = 300

OAUTH_CONSUMER_KEY = 'ButlTUdZbi4s7cAP7dxWVw'
OAUTH_CONSUMER_SECRET = 'LyHAJlbGk2r984OTWSONF7nQHtLqSHumqu7ldduOFeA'

def log(msg, thefile='log.txt', method='a'):
    """Simple debug method"""
    f = open(thefile, method)
    f.write(msg + '\n')
    f.close()

class User(object):
    """A singleton bucket for current user stuff"""
    screen_name = None
    password = None
    is_authenticated = False

    def __call__(self):
        """Singletonness"""
        return self

    def authenticate(self):
        """TODO: some sort of OAuth magic here"""

user = User()

configdict = ConfigParser()

class HappyDate(object):
    """clap clap"""
    months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 
              'Sep', 'Oct', 'Nov', 'Dec']	
    @staticmethod
    def date_str(s):
        """Format the date into something to display
        """
        return s.strftime('%b%d  %H:%M')

class Twyrses(object):
    """ """
    def __init__(self):
        self.status_data = []		
        self.status_list = []
        self.status_count = 0
        self.status_focus = None
        self.header_timeout = datetime.datetime.now()
        self.refresh_timeout = datetime.datetime.now()
        self.last_refresh_command = "/r"
        self.set_refresh_timeout()
        self.exit = False
        self.cmd_buffer = ['']
        self.cmd_buffer_idx = 0

    def main(self):
        """ """
        self.ui = urwid.raw_display.Screen()
        theme = self.get_config_value("THEME", "theme_name")
        if theme:
            self.set_theme([theme])
        else:
            self.set_theme(['default'])

        self.header = urwid.AttrWrap(urwid.Text(''), 'header')
        self.statusbox = urwid.AttrWrap(urwid.Edit(), 'statusbox')
        self.char_count = urwid.AttrWrap(
            urwid.Text(str(CHAR_LIMIT), align='right'), 'char_count')
        self.timeline = urwid.ListBox([])		
        self.top = urwid.Frame(
            header=urwid.Pile([
                urwid.Columns([self.header, ('fixed', 5, self.char_count)]),
                self.statusbox,
                urwid.AttrWrap(urwid.Divider(utf8decode("─")), 'line')
                ]),
            body=self.timeline
        )		
        self.ui.run_wrapper(self.run)

    def run(self):
        """ """
        self.size = self.ui.get_cols_rows()
        self.get_timeline()
        self.draw_timeline()
        self.set_refresh_timeout()

        while 1:
            keys = self.ui.get_input()

            if datetime.datetime.now() > self.header_timeout:			
                self.set_header_text()

            if datetime.datetime.now() > self.refresh_timeout:
                self.handle_command(self.last_refresh_command)
                self.set_refresh_timeout()		

            if self.exit:
                break

            for k in keys:
                if k == 'window resize':
                    self.size = self.ui.get_cols_rows()
                    continue
                elif k == 'page up' or k == 'page down':
                    # only scroll half the rows			
                    self.timeline.keypress((self.size[0], self.size[1]/2), k)
                    if 'bottom' in self.timeline.ends_visible(self.size):
                        self.status_count += 20
                        self.status_focus = self.timeline.get_focus()
                elif k == 'up' or k == 'down':				
                    if k == 'up':
                        self.cmd_buffer_idx += 1
                        self.cmd_buffer_idx = min(
                            self.cmd_buffer_idx,
                            len(self.cmd_buffer)-1)
                    if k == 'down':
                        self.cmd_buffer_idx -= 1
                        self.cmd_buffer_idx = max(self.cmd_buffer_idx, 0)
                    self.statusbox.set_edit_text(
                        self.cmd_buffer[self.cmd_buffer_idx])					

                elif k == 'enter':
                    msg = self.statusbox.edit_text					
                    if len(msg):
                        self.cmd_buffer.insert(1, msg)
                        self.statusbox.set_edit_text("")
                        self.update_char_count()
                        if msg[:1] == '/':
                            self.handle_command(msg)
                        else:
                            self.set_header_text(
                                "updating, be with you in a sec...", 0)
                            self.draw_screen()
                            self.update_status(msg)
                    continue
                else:
                    self.top.keypress(self.size, k)
                    self.update_char_count()

            self.draw_screen()
            self.top.set_focus('header')
            self.draw_screen()

    def handle_command(self, msg):
        """farm out the command to the correct method, 
        or to hell with it,	just go ahead and do it"""
        raw = msg.split(' ')
        if not len(raw[0]) > 1: return
        params = []
        cmd = raw[0][1:]
        if len(raw) > 1:
            params = raw[1:]

        if cmd == 'r' or cmd == 'refresh':
            self.set_header_text("refreshing, hang on a mo...", 0)
            self.draw_screen()
            if len(params) == 0: params = [None]				
            self.get_timeline(cmd=params[0])	
            self.draw_timeline()
            self.last_refresh_command = msg
            self.set_refresh_timeout()

        elif cmd == 'q' or cmd == 'quit':
            self.set_header_text("bye then")
            self.exit = True

        elif cmd == 'f' or cmd == 'follows':
            if not len(params) == 2:
                self.set_header_text("/follows [twittard1] [twittard2]")
                return
            self.set_header_text("just checking...", 0)
            self.draw_screen()			
            self.check_following(params[0], params[1])

        elif cmd == 'a' or cmd == 'auth':
            if not len(params) == 2 and not len(params) == 0:
                self.set_header_text("/auth [username] [password]")
                return			
            if len(params) == 2:
                self.set_header_text("authenticating...", 0)
                user.screen_name = params[0]
                user.password = params[1]
                update_terminal_header(user.screen_name)
            else:
                self.set_header_text("logging out...", 0)	
                user.screen_name = None
                user.password = None		
            self.draw_screen()			
            self.get_timeline()
            self.draw_timeline()

        elif cmd == 'w':
            webbrowser.open("http://www.google.com/")

        elif cmd == 't' or cmd == 'theme':
            self.draw_screen()
            self.ui.clear()
            self.set_theme(params)
            self.get_timeline()
            self.draw_timeline()

        elif cmd == 's' or cmd == 'search':
            return

            if len(params) == 0:
                self.set_header_text("/search [terms]")
                return				
            self.set_header_text("searching, wait on...")
            self.draw_screen()
            # TODO: exapnd this to encompass terms, from_user, to_user
            self.do_search(terms=" ".join(params))
            self.draw_timeline()
            self.last_refresh_command = msg	
            self.set_refresh_timeout()

        elif cmd == '@' or cmd == 'replies':
            self.set_header_text("refreshing, hang on a mo...", 0)
            self.draw_screen()				
            self.get_timeline('replies')	
            self.draw_timeline()
            self.last_refresh_command = msg
            self.set_refresh_timeout()

        elif cmd =='d' or cmd == 'dm' or cmd == 'directmessages':
            self.set_header_text("refreshing, hang on a mo...", 0)
            self.draw_screen()				
            self.get_timeline('dm')	
            self.draw_timeline()
            self.last_refresh_command = msg
            self.set_refresh_timeout()

        elif cmd == 'unfollow':
            if len(params) > 0:
                self.set_header_text('unfollowing....')
                self.draw_screen()
                self.unfollow(params)
                self.get_timeline(cmd=params[0])	
                self.draw_timeline()
                self.last_refresh_command = msg
                self.set_refresh_timeout()

        elif cmd == 'follow':
            if len(params) > 0:
                self.set_header_text('following.....')
                self.draw_screen()
                self.follow(params)
                self.get_timeline(cmd=params[0])	
                self.draw_timeline()
                self.last_refresh_command = msg
                self.set_refresh_timeout()

    def draw_screen(self):
        """ """
        canvas = self.top.render(self.size, focus=True)
        self.ui.draw_screen(self.size, canvas)

    def draw_status(self, status):

        # check if we're receiving a DM or @reply
        # replies have a user
        if hasattr(status, 'user'):

            status =  urwid.Columns([
                ('fixed', 6, urwid.Text(
                    #('date', HappyDate.date_str(status.created_at).encode(code)))),
                    ('date', HappyDate.date_str(status.created_at).encode(code)))),
                ('fixed', len(status.user.screen_name) + 2, 
                 urwid.Text(('name', 
                             ('@%s ' % (status.user.screen_name,)).encode(code)))),
                urwid.Text(status.text.encode(code))		
            ])

            return status
        # dm's don't, they just have a sender_screen_name directly
        elif hasattr(status, 'sender_screen_name'):
            dm =  urwid.Columns([
                ('fixed', 6, urwid.Text(('date', 
                                         HappyDate.date_str(status.created_at).encode(code)))),
                ('fixed', len(status.sender_screen_name) + 2, 
                 urwid.Text(('name', ('@%s ' % 
                                      (status.sender_screen_name,)).encode(code)))),
                urwid.Text(status.text.encode(code))		
            ])

            return dm
        # dunno what we've got here, send it back
        else:
            return None

    def draw_timeline(self):			
        self.timeline.body = urwid.PollingListWalker(
            [self.draw_status(status) for status in self.status_data])	

    def update_char_count(self):
        """ """
        ch_len = len(self.statusbox.get_edit_text())
        if ch_len > CHAR_LIMIT_LOW:
            self.char_count.set_attr('char_count_low')
        elif ch_len > CHAR_LIMIT_MED:
            self.char_count.set_attr('char_count_med')
        else:
            self.char_count.set_attr('char_count')
        self.char_count.set_text(str(CHAR_LIMIT - ch_len))			

    def set_header_text(self, msg=None, timeout=5):
        if timeout:
            self.header_timeout = datetime.datetime.now() + \
                datetime.timedelta(0, timeout)					
        if msg:
            self.header.set_text(msg)
        else:
            if user.screen_name:
                self.header.set_text("@%s" % (user.screen_name,))
            else:
                self.header.set_text("not logged in")

    def set_refresh_timeout(self):
        self.refresh_timeout = datetime.datetime.now() \
            + datetime.timedelta(seconds=REFRESH_TIMEOUT)	

    def set_theme(self, params):
        if len(params) == 0:
            self.header.set_text('Enter a theme name: default/white/black')
            return
        theme_name = params[0]

        if theme_name == 'black':	
            self.ui.register_palette([
                ('header',         'dark gray', 'light gray', 'standout'),
                ('timeline',       'default',   'default'               ),
                ('char_count',     'white',     'light gray', 'bold'    ),
                ('char_count_med', 'dark gray', 'light gray', 'bold'    ),
                ('char_count_low', 'dark red',  'light gray', 'bold'    ),
                ('statusbox',      'default',   'default'               ),
                ('date',           'default',   'default'               ),
                ('name',           'white',     'default',    'bold'    ),
                ('line',           'dark gray', 'default'               )
            ])

            self.update_config_file("THEME", "theme_name", theme_name)
        elif theme_name == 'white':
            self.ui.register_palette([
                ('header',         'light blue', 'dark red', 'standout'),
                ('timeline',       'default',   'default'               ),
                ('char_count',     'black',     'default', 'bold'    ),
                ('char_count_med', 'light blue', 'default', 'bold'    ),
                ('char_count_low', 'light red',  'default', 'bold'    ),
                ('statusbox',      'default',   'default'               ),
                ('date',           'default',   'default'               ),
                ('name',           'light blue',     'default',    'bold'    ),
                ('line',           'dark gray', 'default'               )
            ])	
            self.update_config_file("THEME", "theme_name", theme_name)
        else:	
            self.ui.register_palette([
                ('header',         'default', 'light gray',  'standout'),
                ('timeline',       'default',  'default'               ),
                ('char_count',     'default',  'light gray', 'bold'    ),
                ('char_count_med', 'default',  'light gray', 'bold'    ),
                ('char_count_low', 'default',  'light gray', 'bold'    ),
                ('statusbox',      'default',  'default'               ),
                ('date',           'default',  'default'               ),
                ('name',           'default',  'default',    'bold'    ),
                ('line',           'default',  'default'               )
            ])	
            self.update_config_file("THEME", "theme_name", theme_name)

    #############################################
    ## Twitter Api calls
    #############################################

    def unfollow(self, params):
        """unfollow a user, mostly used for certain 'celebrity twitards'"""
        api = self.get_api()
        for param in params:
            api.destroy_friendship(param)

    def follow(self, params):
        api = self.get_api()
        for param in params:
            api.create_friendship(param)

    def get_timeline(self, cmd=None):
        """Get yer timeline on"""

        api = self.get_api()

        if cmd and not cmd in ('replies', 'dm'):
            try:
                self.status_data = api.GetUserTimeline(cmd)	
            except HTTPError, e:
                if e.code == 401:
                    self.set_header_text(
                        "@%s is protecting their updates" % (cmd,))
                elif e.code == 404:
                    self.set_header_text("can't find @%s" % (cmd,))
        elif user.screen_name:
            try:
                if cmd == "replies":
                    self.status_data = api.mentions()
                # TODO: convert list returned by GetDirectMessages
                elif cmd == "dm":
                    self.status_data = api.direct_messages()
                else:
                    self.status_data = api.home_timeline()					
            except HTTPError, e:
                if e.code == 401:
                    self.set_header_text(
                        "your credentials are somewhat suspect")
        else:
            self.status_data = api.GetPublicTimeline()

    def do_search(self, **kwargs):
        """Does a search!! woo!!"""
        try:
            api = oauthtwitter.OAuthApi(str(user.screen_name), str(user.password))
            self.status_data = api.Search(kwargs)
        except HTTPError, e:
            if e.code == 401:
                self.set_header_text("login to search")

    def update_status(self, text):
        """Update that status"""
        
        api = self.get_api()

        if len(text) > 140:
            raise TwitterError("Text must be less than or equal to 140 characters.")
        api.update_status(text)

    def check_following(self, twittard1, twittard2):
        """Check if one twittard is following another"""
            # weirdly, this works when screen_name and password are None
        api = self.get_api()
        result = api.exists_friendship(twittard1, twittard2)
        return result

    def update_config_file(self, section, setting, value):
        if not configdict.has_section(section):
            configdict.add_section(section)
        configdict.set(section, setting, value)
        f = open('twyrses.conf', 'w')
        configdict.write(f)

    def get_config_value(self, section, setting):
        try:
            configdict.read('twyrses.conf')
        except:
            return None
            
        if not configdict.has_section(section) or not configdict.has_option(section, setting):
            return None
        return configdict.get(section, setting)
    
    def get_api(self):
        auth = tweepy.BasicAuthHandler(str(user.screen_name), str(user.password))
        return tweepy.API(auth)

def update_terminal_header(update):
    print "\033]0;twyrses for " + update +"\007"

def main():
    if len(sys.argv) > 1:	
        try:
            user.screen_name = sys.argv[1]
            user.password = getpass.getpass()
        except:
            sys.stderr.write(__doc__)
            return
    else:
        try:
            configdict.read('twyrses.conf')
            user.screen_name = configdict.get('USER', 'name')
            user.password = configdict.get('USER', 'password')
        except Exception, err:
            print err
            print "config file not found"

    if user.screen_name:
        update_terminal_header(user.screen_name)

    Twyrses().main()

if __name__ == '__main__':
    main()

