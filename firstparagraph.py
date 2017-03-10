#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Public domain; MZMcBride; 2012

debug = False
test_case = False

"""
; PASSING TEST CASES (RETURN SNIPPET)
* Suite
* Metasyntactic variable
* Mubarak
* Barack Obama
* iPod
* Roe v. Wade
* [empty string]
* Atalaya Castle
* Atalaya Castle (Spain)
* William Morrison (dentist)
* Kohei Yoshiyuki
* Mass–energy equivalence
* Novye Aldi massacre
* Paul Simon (politician)
* Hilary Clinton
* FAP 403 RHD
* List of television stations in Bangkok
* Quincy-Voisins
* Dannemarie, Haut-Rhin
* \

; PASSING TEST CASES (RETURN ERROR)
* Suiteeee

; PASSING TEST CASES (RETURN URL)
* Fry's

FAILING TEST CASES
* Schwa
* PIR
* ROC
* blaze of glory
* Key bridge
* S&M (song)
* AT&T
* Dick Dawkins
* wikt:santorum

; TO-DO
* Truncate output more cleanly?
* Remove references?
"""

if debug or test_case:
    import sys
import re
import urllib
import urllib2
import json
import htmlentitydefs

from bs4 import BeautifulSoup

base_url = 'https://en.wikipedia.org'
api_url = base_url+'/w/api.php'

def get_random_article_title():
    values = {'action'      : 'query',
              'list'        : 'random',
              'rnlimit'     : '1',
              'rnnamespace' : '0',
              'format'    : 'json'}
    query_url = api_url+'?'+urllib.urlencode(values)
    url_contents = urllib.urlopen(query_url).read()
    parsed_content = json.loads(url_contents)
    random_article_title = parsed_content['query']['random'][0]['title'].encode('utf-8')
    return random_article_title

def get_page_section(article):
    values = {'action'    : 'query',
              'prop'      : 'revisions',
              'rvlimit'   : '1',
              'rvprop'    : 'content',
              'format'    : 'json',
              'rvsection' : '0',
              'titles'    : article}
    query_url = api_url+'?'+urllib.urlencode(values)+'&redirects'
    if debug:
        print query_url
    url_contents = urllib.urlopen(query_url).read()
    parsed_content = json.loads(url_contents)
    page_id = str(parsed_content['query']['pages'].keys()[0])
    if int(page_id) < 0:
        return False
    page_section = parsed_content['query']['pages'][page_id]['revisions'][0]['*']
    return page_section

def get_parsed_page_section(page_section):
    values = {'action' : 'parse',
              'prop'   : 'text',
              'format' : 'json',
              'text'   : page_section.encode('utf-8')}
    data = urllib.urlencode(values)
    req = urllib2.Request(api_url, data)
    response = urllib2.urlopen(req)
    url_contents = response.read()
    if debug:
        print url_contents
    parsed_content = json.loads(url_contents)
    parsed_page_section = parsed_content['parse']['text']['*']
    return parsed_page_section

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

def is_ambiguous(article):
    clean_article = re.sub(' ', '_', article)
    line = '%s is ambiguous: <%s/wiki/%s>.' % (article, base_url, urllib.quote(clean_article))
    return line

def search_initial_bold(article, page_section):
    clean_page_section = format_line(page_section)
    global line
    first_part = get_first_part(article)
    try:
        coded_line_lower = clean_page_section.decode('utf-8').lower()
    except UnicodeEncodeError:
        coded_line_lower = clean_page_section.encode('utf-8').lower()
    if re.search(r"<p><b>%s" % re.escape(first_part), page_section, re.I):
        line = format_line(page_section)
        if line.endswith(':'):
            line = is_ambiguous(article)
        return line
    elif re.search(r'<p>.*?<b>.*?%s' % re.escape(first_part), page_section[:50], re.I):
        line = format_line(page_section)
        if line.endswith(':'):
            line = is_ambiguous(article)
        return line
    elif first_part.lower().split(' ') <= coded_line_lower.split(' '):
        line = format_line(page_section)
        if line.endswith(':'):
            line = is_ambiguous(article)
        return line
    return False

def search_bold_sentence(article, page_section):
    global line
    for line in page_section.strip('\n').split('\n'):
        if line.startswith('<p>'):
            if re.search(r'<b>'+re.escape(article)+r'</b>', line, re.I):
                line = format_line(line)
                if line.endswith(':'):
                    line = is_ambiguous(article)
                return line
    return False

def search_first_paragraph(article, page_section):
    global line
    first_part = get_first_part(article)
    for line in page_section.strip('\n').split('\n'):
        if line.startswith('<p>'):
            try:
                coded_line_lower = line.decode('utf-8').lower()
            except UnicodeEncodeError:
                coded_line_lower = line.encode('utf-8').lower()
            if article.lower() in coded_line_lower:
                line = format_line(line)
                if line.endswith(':'):
                    line = is_ambiguous(article)
                return line
            elif first_part.split(' ') <= coded_line_lower.split(' '):
                line = format_line(line)
                if line.endswith(':'):
                    line = is_ambiguous(article)
                return line
    return False

def remove_sup(line):
    sup_re = re.compile(r'\s*<sup.+?</sup>\s*')
    for match in sup_re.finditer(line):
        line = re.sub(sup_re, '', line)
    return line

def format_line(line):
    #line = remove_sup(line)
    # Remove all HTML elements
    line = ''.join(BeautifulSoup(line, 'html.parser').findAll(text=True))
    # Clean up any random entities and other bullshit
    line = unescape(line)
    return line

def get_first_part(article):
    first_part = article
    first_part = article.split(' ', 1)[0]
    if article.find(', ') != -1:
        first_part = article.split(', ', 1)[0]
    return first_part

def guess_line(article):
    global line
    page_section = get_page_section(article)
    if not page_section:
        # Article does not exist, just say so
        line = '"%s" does not exist.' % (article)
        return line.encode('utf-8')

    else:
        parsed_page_section = get_parsed_page_section(page_section)
        if debug:
            print parsed_page_section
        # Build a BeautifulSoup object
        soup = BeautifulSoup(parsed_page_section, 'html.parser')
        # Kill all tables!
        for match in soup.findAll('table'):
            if debug:
                print len(soup.findAll('table'))
            match = str(match).decode('utf-8')
            c_match = re.sub(r'\s{2,}', ' ', match)
            c_match = unescape(c_match)
            parsed_page_section = re.sub(r'\s{2,}', ' ', parsed_page_section)
            parsed_page_section = unescape(parsed_page_section)
            if c_match in parsed_page_section and debug:
                print 'this is true'
            parsed_page_section = parsed_page_section.replace(c_match, '')

        # Kill any spurious breaks
        for match in soup.findAll('br'):
            match = str(match).decode('utf-8')
            c_match = re.sub(r'\s{2,}', ' ', match)
            parsed_page_section = re.sub(r'\s{2,}', ' ', parsed_page_section)
            if c_match in parsed_page_section and debug:
                print 'this is true too'
            parsed_page_section = parsed_page_section.replace(c_match, '')

        # Back to a string; strip newlines
        clean_parsed_page_section = parsed_page_section.replace('\n', '')

        # Now iterate through the 'p' elements and try to grab the appropriate one
        soup2 = BeautifulSoup(clean_parsed_page_section, 'html.parser')
        if debug:
            print soup2
        for p in soup2.findAll('p'):
            stripped_p = ''.join(p.findAll(text=True)).encode('utf-8')
            first_part = get_first_part(article)
            if debug:
                print len(first_part)+100
                print len(stripped_p)
                print first_part
                print stripped_p
                print first_part.lower().split(' ')
                print stripped_p.lower().split(' ')
                if first_part.lower().split(' ') < stripped_p.lower().split(' '):
                    print 'penis12'
            if ((first_part.lower().split(' ') < stripped_p.lower().split(' ')
                or len(stripped_p) > (len(first_part)+120))
                and len(stripped_p) > len(first_part)):
                first_parsed_paragraph = str(p).decode('utf-8')
                break
            else:
                first_parsed_paragraph = str(p).decode('utf-8')
        if debug:
            print 'penis2'
            print first_parsed_paragraph

        target_paragraph = first_parsed_paragraph
        if debug:
            print target_paragraph
        clean_target_paragraph = ''.join(BeautifulSoup.BeautifulSoup(first_parsed_paragraph).findAll(text=True))
        if search_initial_bold(article, target_paragraph):
            if debug:
                print 'success?'
        elif search_bold_sentence(article, target_paragraph):
            if debug:
                print 'success!'
        elif search_first_paragraph(article, target_paragraph):
            if debug:
                print 'success.'
        else:
            clean_article = re.sub(' ', '_', article)
            line = '%s/wiki/%s' % (base_url, urllib.quote(clean_article))
            if debug:
                print 'failure :-('
        if len(line) > 400:
            line = line[:400].rsplit(' ', 1)[0] + ' ...'
        return line.encode('utf-8')

if debug or test_case:
    try:
        article = sys.argv[1]
    except IndexError:
        article = get_random_article_title()
    if not article.strip():
        article = get_random_article_title()
    print article
    line = guess_line(article)
    print line
