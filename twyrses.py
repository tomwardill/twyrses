#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# A curses based twitter client
#
# Requires:
#	urwid - http://excess.org/urwid/
# 	python-twitter - http://code.google.com/p/python-twitter/
#
# To do:
#	Ghosting
#		See Timeline from another users POV
#		Sneakily follow people without them knowing
#	Search
#	User info persistence
#	OAuth integration
#   	Send source parameter
#	View ASCII version of user's avatar
#	message / command buffer
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
import twitter
from urllib2 import HTTPError

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
		"""Make a happy date string.
		Prettify the date string returned by the twitter API
		"""
		dl = s.split(' ')
		tl = dl[3].split(':')    
		d1 = datetime.datetime(
			int(dl[5]), HappyDate.months.index(dl[1]), int(dl[2]))
		td = datetime.datetime.today()
		d2 = datetime.datetime(td.year, td.month, td.day -1)
		rtn = "%s:%s" % (tl[0], tl[1])
		if d1 < d2:
			rtn = "%s\n%s.%s\n %s" % (rtn, zfill(dl[2],2), 
				zfill(HappyDate.months.index(dl[1]),2), dl[5])    	
		return rtn
		
	@staticmethod
	def str_date(d):
		"""Make a sad date string.
		Converts a date object into a string vaguely similar to the one 
		returned by the twitter API, which is then reconverted with the
		date_str method. sigh... all a bit futile really.
		"""
		return "xxx %s %s %s:%s:00 +0000 %s" % (HappyDate.months[d.month], 
			zfill(d.day, 2), zfill(d.hour, 2), zfill(d.minute, 2), d.year)

class Twyrses(object):
	""" """
	def __init__(self):
		self.status_data = []		
		self.status_list = []
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
				elif k == 'up' or k == 'down':
				
					# TODO: fix buffer index incrementing
					if k == 'up' and \
					len(self.cmd_buffer) < self.cmd_buffer_idx:
						self.cmd_buffer_idx += 1
										
					if k == 'down' and self.cmd_buffer_idx > 0:
						self.cmd_buffer_idx -= 1
						
					self.set_header_text(str(self.cmd_buffer_idx))
										
					self.statusbox.set_edit_text(
						self.cmd_buffer[self.cmd_buffer_idx])					
				
				elif k == 'enter':
					msg = self.statusbox.edit_text
					self.cmd_buffer.append(msg)
					self.statusbox.set_edit_text("")
					if len(msg):
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

		elif cmd == 't' or cmd == 'theme':
			self.draw_screen()
			self.ui.clear()
			self.set_theme(params)
			self.get_timeline()
			self.draw_timeline()
						
		elif cmd == 's' or cmd == 'search':
			# Search not implemented in the main python-twitter branch yet -
			# seriously considering sacking off python-twitter tbh, I mean
			# it's only a load of json calls innit? will need to anyway
			# once we implement OAuth as it doesn't look like that's 
			# supported yet either.
			# Anyhoo, enough rambling:
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
				('fixed', 6, urwid.Text(('date', HappyDate.date_str(status.created_at).encode(code)))),
				('fixed', len(status.user.screen_name) + 2, urwid.Text(('name', ('@%s ' % (status.user.screen_name,)).encode(code)))),
				urwid.Text(status.text.encode(code))		
			])
		
			return status
		# dm's don't, they just have a sender_screen_name directly
		elif hasattr(status, 'sender_screen_name'):
			dm =  urwid.Columns([
				('fixed', 6, urwid.Text(('date', HappyDate.date_str(status.created_at).encode(code)))),
				('fixed', len(status.sender_screen_name) + 2, urwid.Text(('name', ('@%s ' % (status.sender_screen_name,)).encode(code)))),
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
		if user.screen_name:
			for param in params:
				api = twitter.Api(str(user.screen_name), str(user.password))
				api.DestroyFriendship(param)

	def follow(self, params):
		if user.screen_name:
			for param in params:
				api = twitter.Api(str(user.screen_name), str(user.password))
				api.CreateFriendship(param)
	
	def get_timeline(self, cmd=None):
		"""Get yer timeline on"""
		
		if user.screen_name:
			api = twitter.Api(str(user.screen_name), str(user.password))
		else:
			api = twitter.Api()
			
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
					self.status_data = api.GetReplies()
				# TODO: convert list returned by GetDirectMessages
				elif cmd == "dm":
					self.status_data = api.GetDirectMessages()
				else:
					self.status_data = api.GetFriendsTimeline()					
			except HTTPError, e:
				if e.code == 401:
					self.set_header_text(
						"your credentials are somewhat suspect")
		else:
			self.status_data = api.GetPublicTimeline()
			
	def do_search(self, **kwargs):
		"""Does a search!! woo!!"""
		try:
			api = twitter.Api(str(user.screen_name), str(user.password))
			self.status_data = api.Search(kwargs)
		except HTTPError, e:
			if e.code == 401:
				self.set_header_text("login to search")
	
	def update_status(self, text):
		"""Update that status"""
		try:
			api = twitter.Api(str(user.screen_name), str(user.password))
			api.PostUpdate(text)
			st = twitter.Status(
				created_at=HappyDate.str_date(datetime.datetime.now()),
            	text=text,
            	user=user)
			self.status_data.insert(0, st)
			self.draw_timeline()
		except HTTPError, e:
			if e.code == 401:
				self.set_header_text("login to update")
				
	def check_following(self, twittard1, twittard2):
		"""Check if one twittard is following another"""
		try:
			# weirdly, this works when screen_name and password are None
			api = twitter.Api(str(user.screen_name), str(user.password))
			f = api.GetFriends(user=twittard1)
			if any(u for u in f if u.screen_name == twittard2):
				self.set_header_text("yup, @%s follows @%s" % 
					(twittard1, twittard2))
			else:
				self.set_header_text("nup, @%s does not follow @%s" % 
					(twittard1, twittard2))
		except HTTPError, e:
			if e.code == 401:
				self.set_header_text("login to check who is following who")
			elif e.code == 404:
				self.set_header_text("can't find @%s" % (twittard1,))
				
	def update_config_file(self, section, setting, value):
		if not configdict.has_section(section):
			configdict.add_section(section)
		configdict.set(section, setting, value)
		f = open('twyrses.conf', 'w')
		configdict.write(f)
	
	def get_config_value(self, section, setting):
		if not configdict.has_section(section) or not configdict.has_option(section, setting):
			return None
		return configdict.get(section, setting)
		
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

