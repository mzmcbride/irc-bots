#! /usr/bin/env python
# Public domain; MZMcBride; 2011

import os
import time
import subprocess as sub

import codecs
import poplib
import re
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, task
from email.header import decode_header

import mailsettings as settings

# IRC info
server = 'irc.freenode.net'
trusted = settings.trusted
primary_channel = settings.primary_channel(__file__)

# E-mail info
pop_host = 'pop.googlemail.com'
pop_port = '995'
pop_user = 'reba.the.mail.mistress'
pop_pass = settings.password
max_lines = 5
subject_line_re = re.compile('Subject:')
from_re = re.compile('From:')
to_re = re.compile('To:')

# Debug?
debug = False

class snerkBot(irc.IRCClient):
  realname = 'Reba the Mail Lady'
  nickname = 'reba'
  altnick = 'rebah'
  hostmask = 'nightshade.toolserver.org'
  password = settings.password
  got_Pong = True

  def connectionMade(self):
    irc.IRCClient.connectionMade(self)
    self.lc = task.LoopingCall(self.sendServerPing)
    self.lc.start(60, False)
    self.lc2 = task.LoopingCall(self.retrieveMail)
    if debug:
      self.lc2.start(15, False)
    else:
      self.lc2.start(60, False)

  def connectionLost(self, reason):
    irc.IRCClient.connectionLost(self, reason)

  def signedOn(self):
    for i in settings.channels(__file__):
      self.join(i)

  def irc_ERR_NICKNAMEINUSE(self, prefix, params):
    self.register(self.altnick)

  def kill_self(self):
    sub.Popen('kill %s' % os.getpid(),
              stdout=sub.PIPE,
              stderr=sub.STDOUT,
              shell=True)

  def retrieveMail(self):
    try:
      if debug:
        print 'checking mail...'
      pop = poplib.POP3_SSL(pop_host, pop_port)
      pop.user(pop_user)
      pop.pass_(pop_pass)
      stat = pop.stat()
      if stat[0] > 0:
        for n in range(stat[0]):
          msgnum = n+1
          response, lines, bytes = pop.top(msgnum, max_lines)
          clean_lines = []
          count = 0
          for i in range(len(lines)-1):
            if lines[count+1].replace('\t', ' ').startswith(' '):
              clean_lines.append(lines[count] + lines[count+1])
            elif not lines[count].startswith(' '):
              clean_lines.append(lines[count])
            count += 1
          subject_line = filter(subject_line_re.match, clean_lines)
          subject_line = subject_line[0].split('Subject: ', 1)[1]
          subject_line, subject_encoding = decode_header(subject_line)[0]
          if subject_encoding is not None:
            subject_line = subject_line.decode(subject_encoding).encode('utf-8')
          message_sender = filter(from_re.match, clean_lines)
          name_provided = re.search(r'From: (.+) <.+>', message_sender[0])
          name_not_provided = re.search(r'From: (.+)@.+', message_sender[0])
          if name_provided:
            if debug:
              print 'name provided'
            sender_safe_name = name_provided.group(1)
          elif name_not_provided:
            if debug:
              print 'name not provided'
            sender_safe_name = name_not_provided.group(1)
          sender_safe_name, sender_encoding = decode_header(sender_safe_name)[0]
          if sender_encoding is not None:
            sender_safe_name = sender_safe_name.decode(sender_encoding).encode('utf-8')
          if re.search('To:.+toolserver-announce@', ' '.join(clean_lines)):
            prefix = ''
          elif re.search('To:.+toolserver-l@', ' '.join(clean_lines)):
            prefix = ''
          else:
            if not debug:
              pop.dele(msgnum)
            continue
          final_mail_line = '%s * %s' % (sender_safe_name.strip('"'),
                                         re.sub(r'\t', ' ', re.sub(r'\s{2,}', ' ', subject_line)))
          self.msg(primary_channel, final_mail_line)
          time.sleep(0.5)
          if not debug:
            pop.dele(msgnum)
      pop.quit()
    except:
      pass
    return

  def sendServerPing(self):
    if not self.got_Pong:
      self.kill_self()
    self.got_Pong = False
    self.sendLine('PING %s' % server)

  def irc_PONG(self, prefix, params):
    if params:
      self.got_Pong = True

  def privmsg(self, sender, channel, msg):
    # IRC VARIABLES
    user = sender.split('!', 1)[0]
    try:
      hostmask = sender.split('@', 1)[1]
    except:
      hostmask = ''
    # FIND

    if hostmask == self.hostmask:
      return

    elif channel == self.nickname: # PM'ing with the bot.
      try:
        hostmask = sender.split('@', 1)[1]
      except:
        hostmask = ''
      if re.search(r'^!r(estart)?\b', msg, re.I|re.U):
        self.kill_self()
      elif msg.startswith('#') and hostmask in trusted:
        target = msg.split(' ')[0]
        verb = msg.split(' ')[1]
        nmsg = ' '.join(msg.split(' ')[2:])
        if verb in ['do', 'act']:
          self.describe(target, nmsg)
        elif verb in ['say', 'echo']:
          self.msg(target, nmsg)
      elif hostmask in trusted:
        self.sendLine(msg)
      return

  def action(self, user, channel, msg):
    hostmask = user.split('@', 1)[1]
    user = user.split('!', 1)[0]
    lovefind = re.search(r'(glomps|hugs|snuggles|snuggleglomps|cuddles|licks)( a)? %s' % self.nickname, msg, re.I|re.U)

    if hostmask == self.hostmask:
      return

    elif re.search(r'pets %s' % self.nickname, msg, re.I|re.U):
      self.describe(channel, 'purrs.')
      return

    elif lovefind:
      self.describe(channel, lovefind.group(1) + ' %s.' % user)
      return

    elif re.search(r'tickles %s' % self.nickname, msg, re.I|re.U):
      self.describe(channel, 'giggles.')
      return

class snerkBotFactory(protocol.ClientFactory):
  protocol = snerkBot
  def __init__(self):
    pass

  def clientConnectionLost(self, connector, reason):
    connector.connect()

  def clientConnectionFailed(self, connector, reason):
    reactor.stop()

if __name__ == '__main__':
  f = snerkBotFactory()
  reactor.connectTCP('%s' % server, 8001, f)
  reactor.run()
