#! /usr/bin/env python
# Public domain; MZMcBride; 2011

import os
import random
import re
import subprocess as sub
import urllib
import urlparse
import htmlentitydefs
import BeautifulSoup

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, task

import settings
import firstparagraph

server = 'irc.freenode.net'
trusted = settings.trusted
female = settings.female
exempt = settings.exempt
primary_channel = settings.primary_channel(__file__)
silly_channel = settings.silly_channel(__file__)

f = open(os.environ['HOME']+'/scripts/'+'mother.txt', 'r')
motherly_phrases = f.read().strip('\n').split('\n')
f.close()

f = open(os.environ['HOME']+'/scripts/'+'twats.txt', 'r')
twats = f.read().strip('\n').split('\n')
f.close()

f = open(os.environ['HOME']+'/scripts/'+'sayings.txt', 'r')
sayings = f.read().strip('\n').split('\n')
f.close()

f = open(os.environ['HOME']+'/scripts/'+'logs.txt', 'r')
logimages = f.read().strip('\n').split('\n')
f.close()

def find_urls(msg):
    # This function should return a list of URLs.
    # This function only finds URLs, it does not encode them or do title lookups
    # If the URL is at the beginning of a line, the returned URL will be prepended
    # with a "^"
    urls = []
    # If a line contains only a URL, preprend it with a "^" as a marker as these
    # URLs will be treated a little differently when encoding.
    if re.search(r'^(http[^ ]*)$', msg.strip(), re.I|re.U):
        urls.append('^'+msg)
    # Try to look for URL delimiters; if none are found, just grab the whole thing
    # and pray.
    else:
        if re.search(r'\(http', msg, re.I|re.U):
            graburl = re.compile(r'\((http[^ ]*)\)', re.I|re.U)
        elif re.search(r'\[http', msg, re.I|re.U):
            graburl = re.compile(r'\[(http[^ ]*)\]', re.I|re.U)
        elif re.search(r'<http', msg, re.I|re.U):
            graburl = re.compile(r'<(http[^ ]*)>', re.I|re.U)
        elif re.search(r'\'http', msg, re.I|re.U):
            graburl = re.compile(r'\'(http[^ ]*)\'', re.I|re.U)
        elif re.search(r'"http', msg, re.I|re.U):
            graburl = re.compile(r'"(http[^ ]*)"', re.I|re.U)
        elif re.search(r'>http', msg, re.I|re.U):
            graburl = re.compile(r'>(http[^ ]*)<', re.I|re.U)
        else:
            graburl = re.compile(r'(http[^ ]*)', re.I|re.U)
        # Now iterate through the URLs.
        for url in graburl.finditer(msg):
            # Count instances of '"' and "("/")"; if the count is odd and the message
            # ends with ")" or '"', strip it.
            if (url.group(1).count('"') % 2) != 0 and url.group(1).endswith('"'):
                url = re.search(r'(http[^ ]*)', url.group(1).rstrip('"'), re.I|re.U)
            elif (((url.group(1).count('(')+url.group(1).count(')')) % 2) != 0
                  and url.group(1).endswith(')')):
                url = re.search(r'(http[^ ]*)', url.group(1)[:-1], re.I|re.U)
            if (not re.search(r'\(', url.group(1), re.I|re.U)
                and re.search(r'\)', url.group(1), re.I|re.U)):
                url = re.search(r'(http[^ ]*)', url.group(1).rstrip(')'), re.I|re.U)
            urls.append(url.group(1))
    if urls:
        return urls
    else:
        return False

def encode_urls(urls):
    # This function tries to make URLs a bit more friendly by encoding certain
    # characters (such as parentheses and trailing periods).
    # This function takes a list and iterates through it and returns a list.
    # If the URL is unchanged, it will not be appended to the encoded_urls list.
    encoded_urls = []
    # These keys will be passed to re.sub, so escape properly!
    parentheses_dict = { '\(' : '%28', '\)' : '%29' }
    period_dict = { '\.' : '%2E' }
    for url in urls:
        # This is a URL that was at the beginning of a line; treat it a bit
        # differently.
        if url.startswith('^'):
            # This is important.
            encoded_url = url
            for k,v in parentheses_dict.items():
                encoded_url = re.sub(k, v, encoded_url)
            # We don't want to encode every period, just trailing anchor periods.
            if re.search('#', encoded_url):
                trailing_anchor_periods = re.match(r'(\.*)', encoded_url[::-1], re.I|re.U)
                for k,v in period_dict.items():
                    encoded_url = encoded_url.rstrip('.') + re.sub(k, v, trailing_anchor_periods.group(1))
            # If nothing changed, don't append. Otherwise, strip the prepended
            # marker and append!
            if url != encoded_url:
                encoded_urls.append(encoded_url.lstrip('^'))
        elif re.search(r'(\(|#)', url, re.I|re.U):
            encoded_url = url
            for k,v in parentheses_dict.items():
                encoded_url = re.sub(k, v, encoded_url)
            if re.search(r'%29%29$', encoded_url, re.I|re.U): # Awful hack.
                encoded_url = re.sub('%29%29', '%29', encoded_url)
            # We don't want to encode every period, just trailing anchor periods.
            if re.search('#', encoded_url):
                trailing_anchor_periods = re.match(r'(\.*)', url[::-1], re.I|re.U)
                for k,v in period_dict.items():
                    encoded_url = encoded_url.rstrip('.') + re.sub(k, v, trailing_anchor_periods.group(1))
            if url != encoded_url:
                encoded_urls.append(encoded_url)
    if encoded_urls:
        return encoded_urls
    else:
        return False

def get_url_titles(urls):
    # This function takes a list of URLs and fetches their respective
    # HTML <title> elements. This function returns a list of URL titles.

    # From http://effbot.org/zone/re-sub.htm
    def unescape(text):
        def fixup(m):
            text = m.group(0)
            if text[:2] == "&#":
                # character reference
                try:
                    if text[:3] == "&#x":
                        return unichr(int(text[3:-1], 16))
                    else:
                        return unichr(int(text[2:-1]))
                except ValueError:
                    pass
            else:
                # named entity
                try:
                    text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
                except KeyError:
                    pass
            return text # leave as is
        return re.sub("&#?\w+;", fixup, text)

    url_titles = []
    sites = [
             r'(((old|static)-)?bugzilla|phabricator|lists)\.wikimedia\.org',
             r'youtube\.com',
             r'youtu\.be',
             r'xkcd\.com',
             r'nytimes\.com',
             r'vimeo\.com',
             r'bbc(\.com|\.co\.uk)',
             r'economist\.com',
             r'wikipediareview\.com',
             r'[\w.]*craigslist\.org',
             r'washingtonpost\.com',
            ]
    http_title_find_re = re.compile(r'https?://(www\.|global\.)?(%s)' % '|'.join(sites), re.I|re.U)
    youtube_re = re.compile(r'(youtube\.com|youtu\.be)', re.I|re.U)
    phabricator_re = re.compile(r'phabricator\.wikimedia\.org', re.I|re.U)
    for url in urls:
        url = url.lstrip('^')
        if http_title_find_re.search(url):
            if youtube_re.search(url):
                video_id = get_video_id(url)
                youtube_api = 'https://www.youtube.com/get_video_info?video_id='
                youtube_regular = 'https://www.youtube.com/watch?v='
                youtube_contents_api = urllib.urlopen(youtube_api+video_id).read()
                youtube_parsed = urlparse.parse_qs(youtube_contents_api)
                try:
                    title_tag_text = youtube_parsed['title'][0]
                except KeyError:
                    try:
                        youtube_contents_regular = urllib.urlopen(youtube_regular+video_id).read()
                        meta_title_tag = re.search(
                            r'<meta name="title" content="(.+?)">',
                            youtube_contents_regular,
                            re.DOTALL
                        )
                        title_tag_text = meta_title_tag.group(1)
                    except:
                        continue
            else:
                if phabricator_re.search(url):
                    if re.search(r'phabricator\.wikimedia\.org/[DMPT]\d+', url, re.U):
                        pass
                    else:
                        continue
                response = urllib.urlopen(url).read()
                soup = BeautifulSoup.BeautifulSoup(response)
                title_tag_text = soup.html.head.title.string
            try:
                title_tag_text = title_tag_text.encode('utf-8')
            except UnicodeDecodeError:
                pass
            try:
                title_tag_text = title_tag_text.decode('utf-8')
            except UnicodeDecodeError:
                pass
            title_tag_text_clean = unescape(re.sub(r'\s+', ' ', title_tag_text).strip())
            try:
                title_tag_text_clean = title_tag_text_clean.encode('utf-8')
            except UnicodeDecodeError:
                pass
            url_titles.append(title_tag_text_clean)
    if url_titles:
        return url_titles
    else:
        return False

def get_video_id(url):
    youtube_1_re = re.compile(r'https?://(www\.)?youtube\.com/watch')
    youtube_2_re = re.compile(r'https?://youtu\.be/(.+)')
    if youtube_1_re.search(url):
        query_string = urlparse.urlparse(url).query
        video_id = urlparse.parse_qs(query_string)['v'][0]
    elif youtube_2_re.search(url):
        video_id = youtube_2_re.search(url).group(1)
    return video_id

def get_twit_twats(urls):
    # This function takes a list of URLs and fetches their respective
    # messages if possible. This function returns a list of messages.

    # From http://effbot.org/zone/re-sub.htm
    def unescape(text):
        def fixup(m):
            text = m.group(0)
            if text[:2] == "&#":
                # character reference
                try:
                    if text[:3] == "&#x":
                        return unichr(int(text[3:-1], 16))
                    else:
                        return unichr(int(text[2:-1]))
                except ValueError:
                    pass
            else:
                # named entity
                try:
                    text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
                except KeyError:
                    pass
            return text # leave as is
        return re.sub("&#?\w+;", fixup, text)

    twit_twats = []
    sites = [r'twitter\.com']
    http_twat_find_re = re.compile(r'https?://(www\.|global\.)?(%s)' % '|'.join(sites), re.I|re.U)
    for url in urls:
        url = url.lstrip('^')
        url = url.replace('#!/', '')
        if http_twat_find_re.search(url):
            # https://twitter.com/HannahAyers11/status/208658778764230657
            # https://twitter.com/twatapotmus
            # https://twitter.com/twatapotamus
            # https://twitter.com/#!/jemmabetts
            # https://twitter.com/Dominic_MP/status/211174413805174784
            page_contents = urllib.urlopen(url).read()
            soup = BeautifulSoup.BeautifulSoup(page_contents)
            target_text = soup.find('span', 'entry-content')
            if not target_text:
                target_text = soup.find('p', 'js-tweet-text')
            if not target_text:
                # Fuck it, continue
                continue
            target_text = target_text.renderContents()
            target_text_clean = re.sub(r'\s+', ' ', target_text).strip()
            target_text_cleaner = BeautifulSoup.BeautifulSoup(target_text_clean.decode('utf-8')).findAll(text=True)
            target_text_final = ''.join(target_text_cleaner).encode('utf-8')
            target_text_final = target_text_final.decode('utf-8') # Ugh, really?
            target_text_final = unescape(target_text_final)
            target_text_final = target_text_final.encode('utf-8')
            twit_twats.append(target_text_final)
    if twit_twats:
        return twit_twats
    return False

class snerkBot(irc.IRCClient):
    realname = 'snerk'
    nickname = 'snerk'
    altnick = 'snurk'
    hostmask = 'wikispecies/snerk'
    password = settings.password
    got_pong = True
    first_time = True
    messages = ['Heyyy.', 'Heyyy.']
    actions = ['faps.', 'faps.']
    message_type = ''

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.lc = task.LoopingCall(self.sendServerPing)
        self.lc.start(60, False)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)

    def signedOn(self):
        for i in settings.channels(__file__):
            self.join(i)

    def joined(self, channel):
        if channel.lower() == primary_channel:
            self.msg(primary_channel, '!logs')

    def irc_ERR_NICKNAMEINUSE(self, prefix, params):
        self.register(self.altnick)

    def kill_self(self):
        sub.Popen('kill %s' % os.getpid(),
                  stdout=sub.PIPE,
                  stderr=sub.STDOUT,
                  shell=True)

    def sendServerPing(self):
        if not self.got_pong:
            self.kill_self()
        self.got_pong = False
        self.sendLine('PING %s' % server)

    def irc_PONG(self, prefix, params):
        if params:
            self.got_pong = True

    def demonstrate_emphasis(self, channel):
        # Prevent abuse!
        if channel.lower() != primary_channel:
            return
        sentence = 'I did not steal your yellow pencil.'
        i = 0
        for word in sentence.split(' '):
            reactor.callLater(i,
                              self.msg,
                              channel,
                              sentence.replace(word, '_'+word+'_').replace('._', '_.'))
            i += 2
        return

    def topicUpdated(self, user, channel, newTopic):
        if channel.lower() == primary_channel and not self.first_time:
            urls = find_urls(newTopic)
            if urls:
                encoded_urls = encode_urls(urls)
                url_titles = get_url_titles(urls)
                twit_twats = get_twit_twats(urls)
                if encoded_urls:
                    for url in encoded_urls:
                        self.msg(channel, url)
                elif url_titles:
                    for url_title in url_titles:
                        self.msg(channel, url_title)
                elif twit_twats:
                    for twit_twat in twit_twats:
                        self.msg(channel, twit_twat)
        self.first_time = False
        return

    def privmsg(self, sender, channel, msg):
        user = sender.split('!', 1)[0]
        try:
            hostmask = sender.split('@', 1)[1]
        except:
            hostmask = ''
        # FIND
        hurrfind = re.search(r'(\bh+u+r+)(([,.!?]+)?)(\s|$)+', msg, re.I|re.U)
        durrfind = re.search(r'(\bd+u+r+)', msg, re.I|re.U)
        sayfind = re.search(r'%s.{0,3}(say|echo) [\'"]{1}(.*)[\'"]{1}\.?' % self.nickname, msg, re.I|re.U)
        actfind = re.search(r'%s.{0,3}(do|act) [\'"]{1}(.*)[\'"]{1}\.?' % self.nickname, msg, re.I|re.U)
        repeatfind = re.search(r'(%s.{0,3})?(j|n|w)igg(a|er) wha+t*' % self.nickname, msg, re.I|re.U)

        if sender is not None and channel.lower() == primary_channel:
            self.messages.append(msg)
            self.messages.pop(0)
            if not repeatfind:
                self.message_type = 'message'

        if hostmask == self.hostmask:
            return

        elif repeatfind and channel.lower() == primary_channel:
            if self.message_type == 'action':
                self.describe(channel, self.actions[1])
            else:
                self.msg(channel, self.messages[0])
            self.message_type = 'message'
            return

        elif sayfind:
            self.msg(channel, sayfind.group(2))
            return

        elif actfind:
            self.describe(channel, actfind.group(2))
            return

        elif channel == self.nickname: # PM'ing with the bot.
            try:
                hostmask = sender.split('@', 1)[1]
            except:
                hostmask = ''
            if re.search(r'^!r(estart)?\b', msg, re.I|re.U) and hostmask in trusted:
                self.kill_self()
            elif msg.startswith('fs'):
                target = primary_channel
                nmsg = ' '.join(msg.split(' ')[1:])
                self.msg(target, nmsg)
            elif msg.startswith('fd'):
                target = primary_channel
                nmsg = ' '.join(msg.split(' ')[1:])
                self.describe(target, nmsg)
            elif re.search(r'(^\s*!\s*twat\s*$|^\s*twat\s*!\s*$)', msg, re.I|re.U):
                for channel in [primary_channel, silly_channel]:
                    self.msg(channel, random.choice(twats))
                return
            elif (re.search(r'^\s*!\s*(mother|mom|madre|mama)\s*$', msg, re.I|re.U) or
                  re.search(r'^\s*(mother|mom|madre|mama)\s*!\s*$', msg, re.I|re.U)):
                for channel in [primary_channel, silly_channel]:
                    self.msg(channel, random.choice(motherly_phrases))
                return
            elif msg.startswith('ft'):
                # ft robot
                # ft the
                # ft asdf
                # ft emotionless
                # ft How
                # ft mini-grill
                # ft time for
                target = primary_channel
                nmsg = ' '.join(msg.split(' ')[1:])
                matches = []
                if not nmsg.strip():
                    for channel in [primary_channel, silly_channel]:
                        self.msg(channel, random.choice(twats))
                    return
                for twat in twats:
                    # Normalize input.
                    clean_twat = re.sub(r'[:;,.\'"?]', '', twat.lower())
                    user_message = re.sub(r'[:;,.\'"?]', '', nmsg.lower())
                    if user_message in clean_twat:
                        matches.append(twat)
                if not matches:
                    self.msg(user, 'No matches.')
                elif len(matches) > 1:
                    if len(matches) > 5:
                        self.msg(user, 'Far too many matches.')
                    else:
                        for match in matches:
                            self.msg(user, match)
                else:
                    self.msg(target, matches[0])
            elif msg.startswith('#'):
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

        elif msg.startswith('/wp'):
            # /wp
            # /wp [spaces]
            # /wp ayn_rand
            # /wp Ayn Rand
            # /wp Ayn    Rand
            # /wp   penisssss
            clean_msg = re.sub(r'\s+', ' ', msg)
            if len(clean_msg.split('/wp', 1)[1].strip()) > 0:
                article = clean_msg.split('/wp', 1)[1].strip()
            else:
                article = firstparagraph.get_random_article_title()
            page_section = firstparagraph.get_page_section(article)
            line = firstparagraph.guess_line(article)
            self.msg(channel, line, length=450)
            return

        elif re.search(r'\bihu\b', msg, re.I|re.U):
            self.msg(channel, 'The H stands for "heart."')
            return

        elif (re.search(r'.*\byou know what they say\b.*', msg, re.I|re.U) or
              re.search(r'^\s*!\s*sayings?\s*$', msg, re.I|re.U) or
              re.search(r'^\s*sayings?\s*!\s*$', msg, re.I|re.U)):
            self.msg(channel, random.choice(sayings))
            return

        elif re.search(r'(?<=\W)!logs?(?=\W)|(?<=\W)logs?!(?=\W)', msg, re.I|re.U):
            self.msg(channel, random.choice(logimages))
            return

        elif re.search(r'(^\s*!\s*(pencil|\xe2\x9c\x8e|\xe2\x9c\x8f|\xe2\x9c\x90)\s*$|^\s*(pencil|\xe2\x9c\x8e|\xe2\x9c\x8f|\xe2\x9c\x90)\s*!\s*$)', msg, re.I|re.U):
            self.demonstrate_emphasis(channel)
            return

        elif re.search(r'^(\s*:\s*-?\s*(\||I)+\s*|\s*(\||I)+\s*-?\s*:\s*)', msg, re.I|re.U):
            self.msg(channel, '%s: Why so serious?' % user)
            return

        elif re.search(r'^(\s*:+\s*-?\s*v+\s*|\s*v+\s*-?\s*:+\s*)', msg, re.I|re.U):
            self.msg(channel, '%s: Why so Emufarmers?' % user)
            return

        elif hurrfind and not durrfind:
            moarregex = re.match(r'^(h*)(.*)', hurrfind.group(1), re.I)
            def equalize_case(str1, str2):
                def case(c1, c2):
                    if c1.islower() != c2.islower():
                        return c2.swapcase()
                    return c2
                return ''.join(map(case, str1, str2))
            smsg = equalize_case(moarregex.group(1),
                                 'd' * len(moarregex.group(1))) + moarregex.group(2)
            tmsg = (equalize_case(hurrfind.group(1), smsg))
            self.msg(channel, tmsg + str.replace(hurrfind.group(2).strip(','), str(None), ''))
            return

        elif re.search(r'(\bbastard bot\b)', msg, re.I|re.U):
            self.msg(channel, 'Fuck you.')
            return

        elif re.search(r'http', msg, re.I|re.U):
            urls = find_urls(msg)
            if urls:
                encoded_urls = encode_urls(urls)
                url_titles = get_url_titles(urls)
                twit_twats = get_twit_twats(urls)
                if encoded_urls:
                    for url in encoded_urls:
                        self.msg(channel, url)
                        return
                elif url_titles:
                    for url_title in url_titles:
                        self.msg(channel, url_title)
                        return
                elif twit_twats:
                    for twit_twat in twit_twats:
                        self.msg(channel, twit_twat)
                        return

        elif channel.lower() == '#mediawiki-scripts':
            return

        elif re.search(r'^%s!' % self.nickname, msg, re.I|re.U):
            self.sendLine('TOPIC %s :No faggy shit.' % channel)
            return

        elif re.search(r'^(thanks|thank you|ty),? %s|^%s.{0,3}(thanks|thank you|ty)' % (self.nickname, self.nickname), msg, re.I|re.U):
            self.msg(channel, "You're welcome, you sarcastic fuck.")
            return

        if re.search(r'^%s' % self.nickname, msg, re.I|re.U):
            self.msg(channel, 'Pfft.')
            return

    def action(self, user, channel, msg):
        hostmask = user.split('@', 1)[1]
        user = user.split('!', 1)[0]
        reciprocal_actions = ['glomps',
                              'hugs',
                              'snuggles',
                              'snuggleglomps',
                              'cuddles',
                              'licks',
                              'cuddlefucks',
                              'snugglefucks',
                              'fucks',
                              'rims',
                              'rapes']
        lovefind = re.search(r'(%s)( a)? %s' % ('|'.join(reciprocal_actions), self.nickname), msg, re.I|re.U)

        self.message_type = 'action'
        if user is not None and channel.lower() == primary_channel:
            self.actions.append(msg)
            self.actions.pop(0)

        if hostmask == self.hostmask:
            return

        elif re.search(r'^(\s*:\s*-?\s*(\||I)+\s*|\s*(\||I)+\s*-?\s*:\s*)', msg, re.I|re.U):
            self.msg(channel, '%s: Why so serious?' % user)
            return

        elif re.search(r'^(\s*:+\s*-?\s*v+\s*|\s*v+\s*-?\s*:+\s*)', msg, re.I|re.U):
            self.msg(channel, '%s: Why so Emufarmers?' % user)
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

        elif re.search(r'(stares at|eyes) %s' % self.nickname, msg, re.I|re.U):
            self.msg(channel, 'Creep.')
            return

        elif re.search(r'farts[.]?$', msg, re.I|re.U) and hostmask not in exempt:
            self.msg(channel, 'Ew.')
            return

        elif re.search(r'http', msg, re.I|re.U):
            urls = find_urls(msg)
            if urls:
                encoded_urls = encode_urls(urls)
                if encoded_urls:
                    for url in encoded_urls:
                        self.msg(channel, url)
                        return
                else:
                    url_titles = get_url_titles(urls)
                    if url_titles:
                        for url_title in url_titles:
                            self.msg(channel, url_title)
                            return

        elif re.search(r'mounts %s and rides (him|her|it|%s) around the room' % (self.nickname, self.nickname), msg, re.I|re.U):
            self.msg(channel, ':o')
            self.msg(channel, '\o/')
            if hostmask in female:
                reactor.callLater(3,
                                  self.describe,
                                  channel,
                                  'mounts %s and rides her around the room.' % user)
            else:
                reactor.callLater(3,
                                  self.describe,
                                  channel,
                                  'mounts %s and rides him around the room.' % user)
            return

        elif re.search(r'.*( a)? %s' % self.nickname, msg, re.I|re.U):
            self.msg(channel, 'Fuck you.')
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
    reactor.connectTCP(server, 8001, f)
    reactor.run()
