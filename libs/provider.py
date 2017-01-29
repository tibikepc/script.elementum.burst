# -*- coding: utf-8 -*-

import os
import re
import json
import xbmcaddon
from browser import Browser
from quasar.provider import log, get_setting, set_setting
from providers.definitions import definitions
from utils import ADDON_PATH, get_int, clean_size


def generate_payload(provider, generator, filtering, verify_name=True, verify_size=True):
    filtering.information(provider)
    results = []

    definition = definitions[provider]

    for name, info_hash, uri, size, seeds, peers in generator:
        size = clean_size(size)
        # uri, info_hash = clean_magnet(uri, info_hash)
        v_name = name if verify_name else filtering.title
        v_size = size if verify_size else None
        if filtering.verify(provider, v_name, v_size):
            results.append({"name": name,
                            "uri": uri,
                            "info_hash": info_hash,
                            "size": size,
                            "seeds": get_int(seeds),
                            "peers": get_int(peers),
                            "language": definition["language"] if 'language' in definition else 'en',
                            "provider": '[COLOR %s]%s[/COLOR]' % (definition['color'], definition['name']),
                            "icon": os.path.join(ADDON_PATH, 'libs', 'providers', 'icons', '%s.png' % provider),
                            })
        else:
            log.debug(filtering.reason.encode('ascii', 'ignore'))

    log.debug('>>>>>> %s would send %d torrents to Quasar <<<<<<<' % (provider, len(results)))

    return results


def process(provider, generator, filtering, verify_name=True, verify_size=True):
    log.debug("execute_process for %s with %s" % (provider, repr(generator)))
    definition = definitions[provider]

    browser = Browser()

    if get_setting("use_cloudhole", bool):
        browser.clearance = get_setting('clearance')
        browser.user_agent = get_setting('user_agent')

    log.debug("[%s] Queries: %s" % (provider, filtering.queries))
    log.debug("[%s] Extras:  %s" % (provider, filtering.extras))

    for query, extra in zip(filtering.queries, filtering.extras):
        log.debug("[%s] Before keywords - Query: %s - Extra: %s" % (provider, repr(query), repr(extra)))
        query = filtering.process_keywords(provider, query)
        extra = filtering.process_keywords(provider, extra)
        log.debug("[%s] After keywords  - Query: %s - Extra: %s" % (provider, repr(query), repr(extra)))
        if not query:
            return filtering.results

        url_search = filtering.url.replace('QUERY', query.encode('utf-8'))
        if extra:
            url_search = url_search.replace('EXTRA', extra.encode('utf-8'))
        else:
            url_search = url_search.replace('EXTRA', '')
        url_search = url_search.replace(' ', definition['separator'])

        # MagnetDL fix...
        url_search = url_search.replace('FIRSTLETTER', query[:1])

        # Creating the payload for POST method
        payload = dict()
        for key, value in filtering.post_data.iteritems():
            if 'QUERY' in value:
                payload[key] = filtering.post_data[key].replace('QUERY', query)
            else:
                payload[key] = filtering.post_data[key]

        # Creating the payload for GET method
        data = None
        if filtering.get_data is not None:
            data = dict()
            for key, value in filtering.get_data.iteritems():
                if 'QUERY' in value:
                    data[key] = filtering.get_data[key].replace('QUERY', query.encode('utf-8'))
                else:
                    data[key] = filtering.get_data[key]

        log.debug("-   %s query: %s" % (provider, repr(query)))
        log.debug("--  %s url_search before token: %s" % (provider, url_search))
        log.debug("--- %s using POST payload: %s" % (provider, repr(payload)))
        log.debug("----%s filtering with post_data: %s" % (provider, repr(filtering.post_data)))

        # to do filtering by name.. TODO what?
        filtering.title = query

        if 'token' in definition:
            token_url = definition['base_url'] + definition['token']
            log.debug("Getting token for %s at %s" % (provider, token_url))
            browser.open(token_url)
            token_data = json.loads(browser.content)
            log.debug("Token response for %s: %s" % (provider, repr(token_data)))
            if 'token' in token_data:
                token = token_data['token']
                log.debug("Got token for %s: %s" % (provider, token))
                url_search = url_search.replace('TOKEN', token)
            else:
                log.warning('%s: Unable to get token for %s' % (provider, url_search))

        if 'private' in definition and definition['private']:
            username = get_setting('%s_username' % provider)
            password = get_setting('%s_password' % provider)
            if not username and not password:
                for addon_name in ('script.magnetic.%s' % provider, 'script.magnetic.%s-mc' % provider):
                    for setting in ('username', 'password'):
                        try:
                            value = xbmcaddon.Addon(addon_name).getSetting(setting)
                            set_setting('%s_%s' % (provider, setting), value)
                            if setting == 'username':
                                username = value
                            if setting == 'password':
                                password = value
                        except:
                            pass

            if username and password:
                logged_in = False
                login_object = definition['login_object'].replace('USERNAME', '"%s"' % username).replace('PASSWORD', '"%s"' % password)

                # TODO generic flags in definitions for those...
                if provider == 'alphareign':
                    browser.open(definition['root_url'] + definition['login_path'])
                    if browser.content:
                        csrf_name = re.search(r'name="csrf_name" value="(.*?)"', browser.content)
                        csrf_value = re.search(r'name="csrf_value" value="(.*?)"', browser.content)
                        if csrf_name and csrf_value:
                            login_object = login_object.replace("CSRF_NAME", '"%s"' % csrf_name.group(1))
                            login_object = login_object.replace("CSRF_VALUE", '"%s"' % csrf_value.group(1))
                        else:
                            logged_in = True
                if provider == 'hd-torrents':
                    browser.open(definition['root_url'] + definition['login_path'])
                    if browser.content:
                        csrf_token = re.search(r'name="csrfToken" value="(.*?)"', browser.content)
                        if csrf_token:
                            login_object = login_object.replace('CSRF_TOKEN', '"%s"' % csrf_token.group(1))
                        else:
                            logged_in = True

                if 'token_auth' in definition:
                    # log.debug("[%s] logging in with: %s" % (provider, login_object))
                    if browser.open(definition['root_url'] + definition['token_auth'], post_data=eval(login_object)):
                        token_data = json.loads(browser.content)
                        log.debug("Token response for %s: %s" % (provider, repr(token_data)))
                        if 'token' in token_data:
                            browser.token = token_data['token']
                            log.debug("Auth token for %s: %s" % (provider, browser.token))
                        else:
                            log.warning('%s: Unable to get auth token for %s' % (provider, url_search))
                        log.info('[%s] Token auth successful' % provider)
                    else:
                        log.error("[%s] Token auth failed with response: %s" % (provider, repr(browser.content)))
                        return filtering.results
                elif not logged_in and browser.login(definition['root_url'] + definition['login_path'],
                                                     eval(login_object), definition['login_failed']):
                    log.info('[%s] Login successful' % provider)
                elif not logged_in:
                    log.error("[%s] Login failed: %s", provider, browser.status)
                    log.debug("[%s] Failed login content: %s" % repr(browser.content))
                    return filtering.results

                if logged_in:
                    if provider == 'hd-torrents':
                        browser.open(definition['root_url'] + '/torrents.php')
                        csrf_token = re.search(r'name="csrfToken" value="(.*?)"', browser.content)
                        url_search = url_search.replace("CSRF_TOKEN", csrf_token.group(1))

        log.info("> %s search URL: %s" % (provider, url_search))

        browser.open(url_search, post_data=payload, get_data=data)
        filtering.results.extend(
            generate_payload(provider,
                             generator(provider, browser),
                             filtering,
                             verify_name,
                             verify_size))
    return filtering.results