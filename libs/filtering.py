# -*- coding: utf-8 -*-

import re
import hashlib
from urllib import unquote
from quasar.provider import log, get_setting
from parser.HTMLParser import HTMLParser
from parser.ehp import normalize_string
from providers.definitions import definitions, t411season, t411episode
from utils import Magnet, get_int, get_float, clean_number, size_int


class Filtering:
    def __init__(self):
        self.filters = {
            'filter_480p': ['480p'],
            'filter_720p': ['720p'],
            'filter_1080p': ['1080p'],
            'filter_2k': ['_2k_', '1440p'],
            'filter_4k': ['_4k_', '2160p'],
            'filter_brrip': ['brrip', 'bdrip', 'bluray'],
            'filter_webdl': ['webdl', 'webrip'],
            'filter_hdrip': ['hdrip'],
            'filter_hdtv': ['hdtv'],
            'filter_dvd': ['_dvd_', 'dvdrip'],
            'filter_dvdscr': ['dvdscr'],
            'filter_screener': ['screener', '_scr_'],
            'filter_3d': ['_3d_'],
            'filter_telesync': ['telesync', '_ts_', '_tc_'],
            'filter_cam': ['_cam_', 'hdcam'],
            'filter_trailer': ['trailer']
        }

        qualities_allow = []
        qualities_deny = []
        require = []
        for quality in self.filters:
            if get_setting(quality, bool):
                qualities_allow.extend(self.filters[quality])
            else:
                qualities_deny.extend(self.filters[quality])

        if get_setting('additional_filters', bool):
            accept = get_setting('accept').strip()
            if accept:
                accept = re.split(r',\s?', accept)
                qualities_allow.extend(accept)

            block = get_setting('block')
            if block:
                block = re.split(r',\s?', block)
                qualities_deny.extend(block)

            require = get_setting('require')
            if require:
                require = re.split(r',\s?', require)

        self.quality_allow = qualities_allow
        self.quality_deny = qualities_deny
        self.require_keywords = require

        self.min_size = get_float(get_setting('min_size'))
        self.max_size = get_float(get_setting('max_size'))
        self.check_sizes()

        self.filter_title = False  # TODO ???

        self.queries = []
        self.extras = []

        self.info = dict(title="", titles=[])
        self.get_data = None
        self.post_data = {}
        self.reason = ''
        self.title = ''
        self.results = []
        self.url = ''

    def use_general(self, provider, payload):
        definition = definitions[provider]
        general_query = definition['general_query'] if definition['general_query'] else ''
        log.debug("General URL: %s%s" % (definition['base_url'], general_query))
        self.info = payload
        self.url = "%s%s" % (definition['base_url'], general_query)
        if definition['general_keywords']:
            self.queries = [definition['general_keywords']]
            self.extras = [definition['general_extra']]

    def use_movie(self, provider, payload):
        definition = definitions[provider]
        movie_query = definition['movie_query'] if definition['movie_query'] else ''
        log.debug("Movies URL: %s%s" % (definition['base_url'], movie_query))
        if get_setting('separate_sizes', bool):
            self.min_size = get_float(get_setting('min_size_movies'))
            self.max_size = get_float(get_setting('max_size_movies'))
            self.check_sizes()
        self.info = payload
        self.url = "%s%s" % (definition['base_url'], movie_query)
        if definition['movie_keywords']:
            self.queries = ["%s" % definition['movie_keywords']]
            self.extras = ["%s" % definition['movie_extra']]

    def use_episode(self, provider, payload):
        definition = definitions[provider]
        show_query = definition['show_query'] if definition['show_query'] else ''
        log.debug("Episode URL: %s%s" % (definition['base_url'], show_query))
        if get_setting('separate_sizes', bool):
            self.min_size = get_float(get_setting('min_size_episodes'))
            self.max_size = get_float(get_setting('max_size_episodes'))
            self.check_sizes()
        self.info = payload
        self.url = "%s%s" % (definition['base_url'], show_query)
        if definition['tv_keywords']:
            self.queries = ["%s" % definition['tv_keywords']]
            self.extras = ["%s" % definition['tv_extra'] if definition['tv_extra'] else '']
            # TODO this sucks, tv_keywords should be a list from the start..
            if definition['tv_keywords2']:
                self.queries.append(definition['tv_keywords2'])
                self.extras.append(definition['tv_extra2'] if definition['tv_extra2'] else '')

    def use_season(self, provider, info):
        definition = definitions[provider]
        season_query = definition['season_query'] if definition['season_query'] else ''
        log.debug("Season URL: %s%s" % (definition['base_url'], season_query))
        if get_setting('separate_sizes', bool):
            self.min_size = get_float(get_setting('min_size_seasons'))
            self.max_size = get_float(get_setting('max_size_seasons'))
            self.check_sizes()
        self.info = info
        self.url = "%s%s" % (definition['base_url'], season_query)
        if definition['season_keywords']:
            self.queries = ["%s" % definition['season_keywords']]
            self.extras = ["%s" % definition['season_extra'] if definition['season_extra'] else '']
            if definition['season_keywords2']:
                self.queries.append("%s" % definition['season_keywords2'])
                self.extras.append("%s" % definition['season_extra2'] if definition['season_extra2'] else '')

    def use_anime(self, provider, info):
        definition = definitions[provider]
        anime_query = definition['anime_query'] if definition['anime_query'] else ''
        log.debug("Anime URL: %s%s" % (definition['base_url'], anime_query))
        if get_setting('separate_sizes', bool):
            self.min_size = get_float(get_setting('min_size_episodes'))
            self.max_size = get_float(get_setting('max_size_episodes'))
            self.check_sizes()
        self.info = info
        self.url = "%s%s" % (definition['base_url'], anime_query)
        if self.info['absolute_number']:
            self.info['episode'] = self.info['absolute_number']
        if definition['anime_keywords']:
            self.queries = ["%s" % definition['anime_keywords']]
            self.extras = ["%s" % definition['anime_extra'] if definition['anime_extra'] else '']

    def information(self, provider):
        log.debug('[%s] Accepted keywords: %s' % (provider, self.quality_allow))
        log.debug('[%s] Blocked keywords: %s' % (provider, self.quality_deny))
        log.debug('[%s] Minimum size: %s' % (provider, str(self.min_size) + ' GB'))
        log.debug('[%s] Maximum size: %s' % (provider, str(self.max_size) + ' GB'))

    def check_sizes(self):
        if self.min_size > self.max_size:
            log.warning("Minimum size above maximum, using max size minus 1 GB")
            self.min_size = self.max_size - 1

    def read_keywords(self, keywords):
        """
        Create list from string where the values are marked between curly brackets {example}
        :param keywords: string with the information
        :type keywords: str
        :return: list with collected keywords
        """
        results = []
        if keywords:
            for value in re.findall('{(.*?)}', keywords):
                results.append(value)
        return results

    def process_keywords(self, provider, text):
        """
        Process the keywords in the query
        :param text: string to process
        :type text: str
        :return: str
        """
        keywords = self.read_keywords(text)

        for keyword in keywords:
            keyword = keyword.lower()
            if 'title' in keyword:
                title = self.info["title"]
                language = definitions[provider]['language']
                use_language = None
                if ':' in keyword:
                    use_language = keyword.split(':')[1]
                if use_language and self.info['titles']:
                    try:
                        if use_language not in self.info['titles']:
                            use_language = language
                        if use_language in self.info['titles'] and self.info['titles'][use_language]:
                            title = self.info['titles'][use_language]
                            title = title.replace('.', '')  # FIXME shouldn't be here...
                            log.info("[%s] Using translated '%s' title %s" % (provider, use_language,
                                                                              repr(title)))
                            log.debug("[%s] Translated titles from Quasar: %s" % (provider,
                                                                                  repr(self.info['titles'])))
                    except Exception as e:
                        import traceback
                        log.error("%s failed with: %s" % (provider, repr(e)))
                        map(log.debug, traceback.format_exc().split("\n"))
                text = text.replace('{%s}' % keyword, title)

            if 'year' in keyword:
                text = text.replace('{%s}' % keyword, str(self.info["year"]))

            if 'season' in keyword:
                if '+' in keyword:
                    keys = keyword.split('+')
                    if keys[1] == "t411season":
                        season = str(t411season(self.info['season']))
                    else:
                        season = str(self.info["season"] + get_int(keys[1]))
                elif ':' in keyword:
                    keys = keyword.split(':')
                    season = ('%%.%sd' % keys[1]) % self.info["season"]
                else:
                    season = '%s' % self.info["season"]
                text = text.replace('{%s}' % keyword, season)

            if 'episode' in keyword:
                if '+' in keyword:
                    keys = keyword.split('+')
                    if keys[1] == "t411episode":
                        episode = str(t411episode(self.info['episode']))
                    else:
                        episode = str(self.info["episode"] + get_int(keys[1]))
                elif ':' in keyword:
                    keys = keyword.split(':')
                    episode = ('%%.%sd' % keys[1]) % self.info["episode"]
                else:
                    episode = '%s' % self.info["episode"]
                text = text.replace('{%s}' % keyword, episode)

        return text

    def verify(self, provider, name, size):
        """
        Check the name matches with the title and the filtering keywords, and the size with filtering size values
        :param name: name of the torrent
        :type name: str
        :param size: size of the torrent
        :type size: str
        :return: True is complied with the filtering.  False, otherwise.
        """
        if name is None or name is '':
            self.reason = '[%s] %s' % (provider, '*** Empty name ***')
            return False

        name = self.exception(name)
        name = self.safe_name(name)
        self.title = self.safe_name(self.title) if self.filter_title else name
        normalized_title = normalize_string(self.title)  # because sometimes there are missing accents in the results

        self.reason = "[%s] %70s ***" % (provider, name.decode('utf-8'))

        list_to_verify = [self.title, normalized_title] if self.title != normalized_title else [self.title]

        if self.included(name, keys=list_to_verify, strict=True):
            result = True
            if name:
                if self.require_keywords:
                    for required in self.require_keywords:
                        if required not in name:
                            self.reason += " Missing required keyword"
                            result = False
                            break
                elif not self.included(name, keys=self.quality_allow):
                    self.reason += " Missing any required keyword"
                    result = False
                elif self.included(name, keys=self.quality_deny):
                    self.reason += " Blocked by keyword"
                    result = False

            if size:
                if not self.in_size_range(size):
                    result = False
                    self.reason += " Size out of range"

        else:
            result = False
            self.reason += " Name mismatch"

        return result

    def in_size_range(self, size):
        res = False
        value = size_int(clean_number(size))
        min_size = self.min_size * 1e9
        max_size = self.max_size * 1e9
        if min_size <= value <= max_size:
            res = True
        return res

    def safe_name(self, value):
        """
        Make the name directory and filename safe
        :param value: string to convert
        :type value: str
        :return: converted string
        """
        # First normalization
        value = normalize_string(value)
        value = unquote(value)
        value = self.uncode_name(value)
        # Last normalization, because some unicode char could appear from the previous steps
        value = normalize_string(value)
        value = value.lower()
        keys = {'"': ' ', '*': ' ', '/': ' ', ':': ' ', '<': ' ', '>': ' ', '?': ' ', '|': ' ', '_': ' ',
                "'": '', 'Of': 'of', 'De': 'de', '.': ' ', ')': ' ', '(': ' ', '[': ' ', ']': ' ', '-': ' '}
        for key in keys.keys():
            value = value.replace(key, keys[key])

        value = ' '.join(value.split())

        return value

    def included(self, value, keys, strict=False):
        """
        Check if the keys are present in the string
        :param value: string to test
        :type value: str
        :param keys: values to check
        :type keys: list
        :param strict: if it accepts partial results
        :type strict: bool
        :return: True is any key is included. False, otherwise.
        """
        value = ' ' + value + ' '
        if '*' in keys:
            res = True

        else:
            res1 = []
            for key in keys:
                res2 = []
                for item in re.split(r'\s', key):
                    item = item.replace('_', ' ')
                    if strict:
                        item = ' ' + item + ' '

                    if item.upper() in value.upper():
                        res2.append(True)

                    else:
                        res2.append(False)

                res1.append(all(res2))
            res = any(res1)

        return res

    def uncode_name(self, name):
        """
        Convert all the &# codes to char, remove extra-space and normalize
        :param name: string to convert
        :type name: str
        :return: converted string
        """
        name = name.replace('<![CDATA[', '').replace(']]', '')
        name = HTMLParser().unescape(name.lower())

        return name

    def exception(self, title=None):
        """
        Change the title to the standard name in the torrent sites
        :param title: title to check
        :type title: str
        :return: the new title
        """
        if title:
            title = title.lower()
            title = title.replace('csi crime scene investigation', 'CSI')
            title = title.replace('law and order special victims unit', 'law and order svu')
            title = title.replace('law order special victims unit', 'law and order svu')
            title = title.replace('S H I E L D', 'SHIELD')

        return title


def apply_filters(results_list):
    """
    Filter the results
    :param results_list: values to filter
    :type results_list: list
    :return: list of filtered results
    """
    results_list = cleanup_results(results_list)
    log.debug("Filtered results: %s" % repr(results_list))
    # results_list = sort_by_quality(results_list)
    # log.info("Sorted results: %s" % repr(results_list))

    return results_list


def cleanup_results(results_list):
    """
    Remove dupes and sort by seeds
    :param results_list: values to filter
    :type results_list: list
    :return: list of cleaned results
    """
    if len(results_list) == 0:
        return []

    hashes = []
    filtered_list = []
    for result in results_list:
        if not result['seeds']:
            continue

        if not result['uri']:
            if not result['name']:
                continue
            try:
                log.warning('[%s] No URI for %s' % (result['provider'][16:-8], repr(result['name'])))
            except Exception as e:
                import traceback
                log.warning("%s logging failed with: %s" % (result['provider'], repr(e)))
                map(log.debug, traceback.format_exc().split("\n"))
            continue

        hash_ = result['info_hash'].upper()

        if not hash_:
            if result['uri'] and result['uri'].startswith('magnet'):
                hash_ = Magnet(result['uri']).info_hash.upper()
            else:
                hash_ = hashlib.md5(result['uri']).hexdigest()

        try:
            log.debug("[%s] Hash for %s: %s" % (result['provider'][16:-8], repr(result['name']), hash_))
        except Exception as e:
            import traceback
            log.warning("%s logging failed with: %s" % (result['provider'], repr(e)))
            map(log.debug, traceback.format_exc().split("\n"))

        if not any(existing == hash_ for existing in hashes):
            filtered_list.append(result)
            hashes.append(hash_)

    return sorted(filtered_list, key=lambda r: (get_int(r['seeds'])), reverse=True)


def check_quality(text=""):
    """
    Get the quality values from string
    :param text: string with the name of the file
    :type text: str
    :return:
    """
    text = text.lower()
    quality = "480p"

    if "480p" in text:
        quality = "480p"

    if "720p" in text:
        quality = "720p"

    if "1080p" in text:
        quality = "1080p"

    if "3d" in text:
        quality = "1080p"

    if "4k" in text:
        quality = "2160p"

    return quality


def sort_by_quality(results_list):
    """
    Apply sorting based on seeds and quality
    :param results_list: list of values to be sorted
    :type results_list: list
    :return: list of sorted results
    """
    log.info("Applying quality sorting")
    for result in results_list:
        # hd streams
        quality = check_quality(result['name'])
        if "1080p" in quality:
            result['quality'] = 3
            result['hd'] = 1

        elif "720p" in quality:
            result['quality'] = 2
            result['hd'] = 1

        else:
            result['quality'] = 1
            result['hd'] = 0

    return sorted(results_list, key=lambda r: (r["seeds"], r['hd'], r['quality'], r["peers"]), reverse=True)