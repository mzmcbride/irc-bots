#! /usr/bin/env python
# -*- encoding: utf-8 -*-
# Public domain; MZMcBride; 2018

import os
import re
import subprocess as sub
import urllib
import urlparse
import htmlentitydefs

from bs4 import BeautifulSoup
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, task

import firstparagraph

server = 'irc.mozilla.org'
channels = [u'#☭☮⚀⚀']

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
    brackets_dict = {
        '\(' : '%28',
        '\)' : '%29',
        '\[' : '%5B',
        '\]' : '%5D',
    }
    period_dict = { '\.' : '%2E' }
    for url in urls:
        # This is a URL that was at the beginning of a line; treat it a bit
        # differently.
        if url.startswith('^'):
            # This is important.
            encoded_url = url
            for k, v in brackets_dict.items():
                encoded_url = re.sub(k, v, encoded_url)
            # We don't want to encode every period, just trailing anchor periods.
            if re.search('#', encoded_url):
                trailing_anchor_periods = re.match(r'(\.*)', encoded_url[::-1], re.I|re.U)
                for k, v in period_dict.items():
                    encoded_url = encoded_url.rstrip('.') + re.sub(k, v, trailing_anchor_periods.group(1))
            # If nothing changed, don't append. Otherwise, strip the prepended
            # marker and append!
            if url != encoded_url:
                encoded_urls.append(encoded_url.lstrip('^'))
        elif re.search(r'(\(|#|\[)', url, re.I|re.U):
            encoded_url = url
            for k, v in brackets_dict.items():
                encoded_url = re.sub(k, v, encoded_url)
            if re.search(r'%29%29$', encoded_url, re.I|re.U): # Awful hack.
                encoded_url = re.sub('%29%29', '%29', encoded_url)
            # We don't want to encode every period, just trailing anchor periods.
            if re.search('#', encoded_url):
                trailing_anchor_periods = re.match(r'(\.*)', url[::-1], re.I|re.U)
                for k, v in period_dict.items():
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
             r'npr\.org',
             r'vimeo\.com',
             r'bbc(\.com|\.co\.uk)',
             r'economist\.com',
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
                    if re.search(r'phabricator\.wikimedia\.org/[DMPTU]\d+', url, re.U):
                        pass
                    else:
                        continue
                # urllib is getting a "400 Bad Request" response with URLs
                # that contain anchors :-(
                url = url.split('#', 1)[0]
                response = urllib.urlopen(url).read()
                soup = BeautifulSoup(response, 'html.parser')
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
            # https://twitter.com/drewtoothpaste/status/313418036218585088
            # https://twitter.com/kylegriffin1/status/1025166892468789248
            # https://twitter.com/originalspin/status/1025162025981239297?s=19
            page_contents = urllib.urlopen(url).read()
            soup = BeautifulSoup(page_contents, 'html.parser')
            target_text = soup.find('span', 'entry-content')
            if not target_text:
                target_text = soup.find('p', 'js-tweet-text')
            if not target_text:
                # Fuck it, continue
                continue
            target_text = target_text.get_text()
            target_text_clean = re.sub(r'\s+', ' ', target_text).strip()
            target_text_cleaner = BeautifulSoup(target_text_clean, 'html.parser').findAll(text=True)
            target_text_cleanest = ''.join(target_text_cleaner)
            target_text_tweaked = target_text_cleanest.replace('pic.twitter.com/', ' https://pic.twitter.com/')
            target_text_freer_urls = re.sub(r'([^ ])(https?://)', '\g<1> \g<2>', target_text_tweaked)
            target_text_final = unescape(target_text_freer_urls).encode('utf-8')
            twit_twats.append(target_text_final)
    if twit_twats:
        return twit_twats
    return False

def get_mast_toots(urls):
    # This function takes a list of URLs and fetches their respective
    # messages if possible. This function can return a list of messages.

    mast_toots = []
    for url in urls:
        url = url.lstrip('^')
        if url.find('@') != -1:
            # https://mastodon.technology/@legoktm/99668580131269588
            # https://mastodon.technology/@legoktm/99635890120340359
            # https://social.coop/@eloquence/99786019927660750
            # https://medium.com/@icelevel/whos-left-mariame-26ed2237ada6
            page_contents = urllib.urlopen(url).read()
            soup = BeautifulSoup(page_contents, 'html.parser')
            target_text = soup.find('meta', property='og:description')
            if not target_text:
                # Fuck it, continue
                continue
            target_text = target_text['content']
            target_text_clean = re.sub(r'\s+', ' ', target_text).strip()
            target_text_cleaner = BeautifulSoup(target_text_clean, 'html.parser').findAll(text=True)
            target_text_cleanest = ''.join(target_text_cleaner)
            target_text_final = target_text_cleanest.encode('utf-8')
            mast_toots.append(target_text_final)
    if mast_toots:
        return mast_toots
    return False

class slackerBot(irc.IRCClient):
    realname = 'slacker'
    nickname = 'slacker'
    altnick = 'slackerr'
    password = ''
    got_pong = True
    first_time = True

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.lc = task.LoopingCall(self.sendServerPing)
        self.lc.start(60, False)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)

    def signedOn(self):
        for i in channels:
            self.join(i)

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

    def topicUpdated(self, user, channel, newTopic):
        if not self.first_time:
            urls = find_urls(newTopic)
            if urls:
                encoded_urls = encode_urls(urls)
                url_titles = get_url_titles(urls)
                twit_twats = get_twit_twats(urls)
                mast_toots = get_mast_toots(urls)
                if encoded_urls:
                    for url in encoded_urls:
                        self.msg(channel, url)
                elif url_titles:
                    for url_title in url_titles:
                        self.msg(channel, url_title)
                elif twit_twats:
                    for twit_twat in twit_twats:
                        self.msg(channel, twit_twat)
                elif mast_toots:
                    for mast_toot in mast_toots:
                        self.msg(channel, mast_toot)
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

        if user == self.nickname:
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
            if re.search(r'^!r(estart)?\b', msg, re.I|re.U):
                self.kill_self()
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

        elif hurrfind and not durrfind:
            print('hi')
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

        elif re.search(r'http', msg, re.I|re.U):
            urls = find_urls(msg)
            if urls:
                encoded_urls = encode_urls(urls)
                url_titles = get_url_titles(urls)
                twit_twats = get_twit_twats(urls)
                mast_toots = get_mast_toots(urls)
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
                elif mast_toots:
                    for mast_toot in mast_toots:
                        self.msg(channel, mast_toot)
                        return

        greetingfind = re.search(r'((hi+|hello|hey+|greetings)[, ]*)%s' % self.nickname, msg, re.I|re.U)
        if greetingfind:
            self.msg(channel, greetingfind.group(1)[0].upper() + greetingfind.group(1)[1:] + '%s.' % user)
            return

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

        if user == self.nickname:
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

        elif re.search(r'farts[.]?$', msg, re.I|re.U):
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

class slackerBotFactory(protocol.ClientFactory):
    protocol = slackerBot
    def __init__(self):
        pass

    def clientConnectionLost(self, connector, reason):
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        reactor.stop()

if __name__ == '__main__':
    f = slackerBotFactory()
    reactor.connectTCP(server, 6667, f)
    reactor.run()
