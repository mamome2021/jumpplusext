#!/usr/bin/env python3
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, wait
from itertools import repeat
import multiprocessing
from pathlib import Path
import signal
import sys
import traceback
import urllib.parse

import httpx

class ExtractorBase(ABC):

    # Override this for setting extension of downloaded images
    image_extension = None

    help_text_basic = '''用法：
{0} {1}
{0} search QUERY
    搜索漫畫。QUERY為關鍵字
{0} list-chapter COMIC_ID
    列出漫畫章節。COMIC_ID為漫畫的ID
{0} dl [-o 下載位置] COMIC_ID CHAPTER_ID ...
    下載漫畫。COMIC_ID為漫畫的ID，CHAPTER_ID為章節的ID。可指定多個CHAPTER_ID
{0} dl-all [-o 下載位置] COMIC_ID ...
    下載漫畫所有章節。COMIC_ID為漫畫的ID。可指定多個COMIC_ID
{0} dl-seq [-o 下載位置] COMIC_ID ... INDEX
    依照章節序號下載漫畫。COMIC_ID為漫畫的ID，可指定多個COMIC_ID。INDEX為章節在list-chapter中的序號，序號前加r代表反序。也可使用-代表範圍。
'''
    help_text_with_bought = (help_text_basic +
'''{0} list-comic
    列出已購漫畫
{0} list-bought-chapter COMIC_ID
    列出已購漫畫章節。COMIC_ID為漫畫的ID
''')
    help_text_with_removed = (help_text_with_bought +
'''{0} dl-removed [-o 下載位置] COMIC_ID CHAPTER_ID ...
    下載下架漫畫。COMIC_ID為漫畫的ID，CHAPTER_ID為章節的ID。可指定多個CHAPTER_ID
{0} dl-all-removed [-o 下載位置] COMIC_ID ...
    下載下架漫畫所有章節。COMIC_ID為漫畫的ID。可指定多個COMIC_ID
{0} dl-seq-removed [-o 下載位置] COMIC_ID ... INDEX
    依照章節序號下載下架漫畫。COMIC_ID為漫畫的ID，可指定多個COMIC_ID。INDEX為章節在list-bought-chapter中的序號，序號前加r代表反序。也可使用-代表範圍。
''')

    pool = None

    @abstractmethod
    def name(self):
        """Website name of extractor, for filename of session file"""
        return ''

    def __init__(self):
        """Create extractor class, read session file"""

        # Override this with ProcessPoolExecutor for multiprocessing
        self.Executor = ThreadPoolExecutor
        self.is_interrupted = False

        # 讀取登錄信息
        self.token = ''
        try:
            session_file = Path(__file__).parent / (self.name + '-session')
            with open(session_file, 'r') as f:
                self.token = f.read().rstrip()
        except:
            pass

        # 讀取設定
        self.config = {
            'threads': 4,
            'retries': 20
        }
        try:
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                # In PyInstaller bundle
                config_filename = Path(sys.executable).parent / f'{self.name}-config.txt'
            else:
                config_filename = Path(__file__).parent / f'{self.name}-config.txt'
            if config_filename.exists():
                with config_filename.open('r', encoding='utf-8') as config_file:
                    lines = config_file.read().split('\n')
                for line in lines:
                    option = line.split()
                    if len(option) == 0:
                        continue
                    if option[0] == 'threads':
                        self.config['threads'] = int(option[1])
                    elif option[0] == 'retries':
                        self.config['retries'] = int(option[1])
        except Exception:
            print(traceback.format_exc())

    def main(self):
        signal.signal(signal.SIGINT, self.interrupt)
        self.arg_parse()

    def interrupt(self, sig, frame):
        if not multiprocessing.parent_process():
            print('收到中斷訊號，將結束程式')
        self.is_interrupted = True

    @abstractmethod
    def show_help(self):
        """Show help text, should probably output
        help_text or help_text_with_removed and format()"""
        pass

    def str_to_index(self, string, length):
        """Convert user input string to index of chapter list

        :param string: user input string
        :type string: str
        :param length: length of chapter list
        :type length: int
        :return: List of index
        :rtype: list[int]
        """
        def str_to_int(s, length):
            if s[0] == 'r':
                return length - int(s[1:])
            else:
                return int(s) - 1

        if '-' in string:
            start, end = [str_to_int(i, length) for i in string.split('-')]
            if start > end:
                return range(start, end - 1, -1)
            else:
                return range(start, end + 1)
        else:
            return [str_to_int(string, length)]

    def get_location(self):
        """Parse sys.argv and determine download location

        :return: Location for download file
        :rtype: str
        """
        try:
            pos = sys.argv.index('-o')
            location = sys.argv[pos + 1]
            del sys.argv[pos:pos + 2]
            return location
        except ValueError:
            return ''
        except IndexError:
            self.show_help()
            sys.exit(0)

    def arg_parse(self):
        """Parse sys.argv and do action"""
        if len(sys.argv) < 2:
            self.show_help()
            sys.exit(0)
        elif sys.argv[1] == 'login':
            if len(sys.argv) < 3:
                self.show_help()
                sys.exit(0)
            self.login(sys.argv[2:])
        elif sys.argv[1] == 'list-comic':
            if len(sys.argv) != 2:
                self.show_help()
                sys.exit(0)
            self.showBoughtComicList()
        elif sys.argv[1] == 'search':
            if len(sys.argv) < 3:
                self.show_help()
                sys.exit(0)
            self.showSearchComicList(sys.argv[2])
        elif sys.argv[1] == 'list-chapter':
            if len(sys.argv) != 3:
                self.show_help()
                sys.exit(0)
            self.showChapterList(sys.argv[2])
        elif sys.argv[1] == 'list-bought-chapter':
            if len(sys.argv) != 3:
                self.show_help()
                sys.exit(0)
            self.showBoughtChapterList(sys.argv[2])
        elif sys.argv[1] == 'dl':
            location = self.get_location()
            if len(sys.argv) < 4:
                self.show_help()
                sys.exit(0)
            for chapter_id in sys.argv[3:]:
                if self.is_interrupted:
                    return
                try:
                    self.downloadChapter(sys.argv[2], chapter_id, location)
                except Exception as e:
                    print(traceback.format_exc())
                    print(f'章節 {chapter_id} 下載失敗：{e}')
        elif sys.argv[1] == 'dl-seq' or sys.argv[1] == 'dl-all':
            if sys.argv[1] == 'dl-all':
                sys.argv.append("1-r1")
            location = self.get_location()
            if len(sys.argv) < 4:
                self.show_help()
                sys.exit(0)
            for comic in sys.argv[2:-1]:
                if self.is_interrupted:
                    return
                try:
                    chapter_list = self.getChapterList(comic)
                except Exception as e:
                    print(f'漫畫 {comic} 無法獲得章節清單：{e}')
                    continue

                for index in self.str_to_index(sys.argv[-1], len(list(chapter_list))):
                    try:
                        chapter_id = str(chapter_list[index][0])
                    except IndexError:
                        print(f'錯誤：沒有第{index + 1}章')
                        continue
                    if self.is_interrupted:
                        return
                    try:
                        self.downloadChapter(comic, chapter_id, location)
                    except Exception as e:
                        print(traceback.format_exc())
                        print(f'章節 {chapter_id} 下載失敗：{e}')
        elif sys.argv[1] == 'dl-removed':
            location = self.get_location()
            if len(sys.argv) < 4:
                self.show_help()
                sys.exit(0)
            for chapter_id in sys.argv[3:]:
                if self.is_interrupted:
                    return
                try:
                    self.downloadRemovedChapter(sys.argv[2], chapter_id, location)
                except Exception as e:
                    print(f'章節 {chapter_id} 下載失敗：{e}')
        elif sys.argv[1] == 'dl-seq-removed' or sys.argv[1] == 'dl-all-removed':
            if sys.argv[1] == 'dl-all-removed':
                sys.argv.append("1-r1")
            location = self.get_location()
            if len(sys.argv) < 4:
                self.show_help()
                sys.exit(0)
            for comic in sys.argv[2:-1]:
                if self.is_interrupted:
                    return
                try:
                    chapter_list = self.getBoughtChapterList(comic)
                except Exception as e:
                    print(f'漫畫 {comic} 無法獲得章節清單：{e}')
                    continue
                for index in self.str_to_index(sys.argv[-1], len(list(chapter_list))):
                    try:
                        chapter_id = str(chapter_list[index][0])
                    except IndexError:
                        print(f'錯誤：沒有第{index + 1}章')
                        continue
                    if self.is_interrupted:
                        return
                    try:
                        self.downloadRemovedChapter(comic, chapter_id, location)
                    except Exception as e:
                        print(f'章節 {chapter_id} 下載失敗：{e}')
        else:
            self.show_help()

    def decrypt_image(self, encrypted, idx, image_url, decrypt_info):
        """Override this if downloaded images need to be decrypted

        :param encrypted: encrypted image content
        :type encrypted: bytes
        :param idx: index (page number) of image, starts from 1
        :type idx: int
        :param image_url: url of image
        :type image_url: str
        :param decrypt_info: Information for image decryption
        :return: decrypted image
        :rtype: bytes
        """
        return encrypted

    def get_request(self, url, headers=None):
        """Wrapper of httpx.get() to retry failed request"""
        for i in range(self.config['retries']):
            if self.is_interrupted:
                return
            try:
                return httpx.get(url, headers=headers)
            except Exception as e:
                if i == self.config['retries'] - 1:
                    raise e

    def post_request(self, url, data=None, json=None, headers=None):
        """Wrapper of httpx.post() to retry failed request"""
        for i in range(self.config['retries']):
            if self.is_interrupted:
                return
            try:
                return httpx.post(url, data=data, json=json, headers=headers)
            except Exception as e:
                if i == self.config['retries'] - 1:
                    raise e

    def download_img(self, idx, image, headers, path, decrypt_info):
        """Called by download_worker to download image

        :param idx: index (page number) of image, starts from 1
        :type idx: int
        :param image: url of image
        :type image: str
        :param headers: headers used for image download
        :type headers: dict
        :param path: Download location
        :type path: Path
        :param decrypt_info: Information for image decryption
        """
        try:
            if self.is_interrupted:
                return
            if self.image_extension:
                ext = self.image_extension
            else:
                image_name = urllib.parse.urlparse(image).path
                ext = Path(image_name).suffix
                # Fix Kuaikan and Kakao extension
                if ext == '.h' or ext == '.cef':
                    ext = Path(Path(image_name).stem).suffix
                if not ext:
                    ext = '.jpg'
            filename = Path(path, str(idx).zfill(3) + ext)
            if filename.exists():
                return

            r = self.get_request(image, headers=headers)
            content = self.decrypt_image(r.content, idx, image, decrypt_info)
            with filename.open('wb') as f:
                f.write(content)
        except Exception as e:
            print(traceback.format_exc())
            print(path / str(idx).zfill(3), '下載失敗：', e)

    def download_list(self, image_download):
        """Download images

        :param image_download: ImageDownload object
        :type image_download: ImageDownload
        """
        if self.is_interrupted:
            return
        root = image_download.root
        comic_title = self.fix_filename(image_download.comic_title)
        chapter_title = self.fix_filename(image_download.chapter_title)
        print(f'下載{comic_title}/{chapter_title}')
        path = Path(root, comic_title, chapter_title)
        path.mkdir(parents=True, exist_ok=True)
        if not ExtractorBase.pool:
            ExtractorBase.pool = self.Executor(max_workers=self.config['threads'])
        futures = [ExtractorBase.pool.submit(self.download_img, idx + 1, url, image_download.headers, path, image_download.decrypt_info) for idx, url in enumerate(image_download.urls)]
        #wait(futures)

    def fix_filename(self, name):
        """Convert invalid filename to valid name

        :param name: comic or chapter name, which may be invalid filename
        :type name: str
        :return: valid filename
        :rtype: str
        """
        return name.replace('<', '＜').replace('>', '＞').replace(':', '：') \
                   .replace('"', '＂').replace('/', '⧸').replace('\\', '⧹') \
                   .replace('|', '│').replace('?', '？').replace('*', '＊') \
                   .replace('\t', ' ').replace('\x08', ' ').rstrip(' .')

    def login(self, token):
        """Write login information (token) to local session file

        :param token: User input token
        :type token: list[str]
        """
        if len(token) == 0:
            self.show_help()
            sys.exit(0)
        session_file = Path(__file__).parent / (self.name + '-session')
        with open(session_file, 'w') as f:
            for i in token:
                f.write(i + '\n')

    @abstractmethod
    def getChapterList(self, comic_id):
        """Fetch chapter list from website

        :param comic_id: id of comic
        :type comic_id: str
        :return: List of chapter, which is (id, title, is_locked)
        :rtype: list[tuple[str, str, bool]] or list[tuple[str, str]]
        """
        pass

    def showChapterList(self, comic_id):
        """Display chapter list

        :param comic_id: id of comic
        :type comic_id: str
        """
        for index, i in enumerate(self.getChapterList(comic_id)):
            if len(i) > 2 and i[2]:
                print('(鎖)', index + 1, i[1])
            else:
                print(index + 1, i[1])

    @abstractmethod
    def downloadChapter(self, comic_id, chapter_id, root):
        """Fetch image list of chapter and download

        :param comic_id: id of comic
        :type comic_id: str
        :param chapter_id: id of chapter
        :type chapter_id: str
        :param root: root directory of download location
        :type root: str
        """
        pass

    def getBoughtComicList(self):
        """Fetch bought comic list from website

        :return: List of comic, which is (id, title)
        :rtype: list[tuple[str, str]]
        """
        self.show_help()
        sys.exit(0)

    def showBoughtComicList(self):
        """Display bought comic list"""
        for i in self.getBoughtComicList():
            print(i[0], i[1])

    def getBoughtChapterList(self, comic_id):
        """Fetch bought chapter list from website

        :param comic_id: id of comic
        :type comic_id: str
        :return: List of chapter, which is (id, title)
        :rtype: list[tuple[str, str]]
        """
        self.show_help()
        sys.exit(0)

    def showBoughtChapterList(self, comic_id):
        """Display bought chapter list

        :param comic_id: id of comic
        :type comic_id: str
        """
        for index, i in enumerate(self.getBoughtChapterList(comic_id)):
            print(index + 1, i[1])

    def downloadRemovedChapter(self, comic_id, chapter_id, root):
        """Fetch image list of chapter of removed comic and download

        :param comic_id: id of comic
        :type comic_id: str
        :param chapter_id: id of chapter
        :type chapter_id: str
        :param root: root directory of download location
        :type root: str
        """
        self.show_help()
        sys.exit(0)

    def searchComic(self, query):
        """Search comic with query

        :param query: search keyword
        :type query: str
        :return: List of comic, which is (id, title)
        :rtype: list[tuple[str, str]]
        """
        self.show_help()
        sys.exit(0)

    def showSearchComicList(self, query):
        """Display search result comic list

        :param query: search keyword
        :type query: str
        """
        for i in self.searchComic(query):
            print(i[0], i[1])

class ImageDownload:
    """Class to pass download information to download_list()

    :param urls: List of image url to download
    :type urls: list[str]
    :param headers: Headers used for image download
    :type headers: dict
    :param root: root directory of download location
    :type root: str
    :param comic_title: comic title
    :type comic_title: str
    :param chapter_title: chapter title
    :type chapter_title: str
    """

    def __init__(self, root, comic_title, chapter_title):
        """Create ImageDownload object

        :param root: root directory of download location
        :type root: str
        :param comic_title: comic title
        :type comic_title: str
        :param chapter_title: chapter title
        :type chapter_title: str
        """
        self.urls = []
        self.headers = {}
        self.root = root
        self.comic_title = comic_title
        self.chapter_title = chapter_title
        self.decrypt_info = None
import hashlib
import sys



class Extractor(ExtractorBase):
    name = 'jumpplus'

    def __init__(self):
        super().__init__()
        self.device_id = hashlib.md5(self.token.encode()).hexdigest()[:16]
        self.headers = {
            # x-giga-device-id required for 初回無料
            'user-agent': 'ShonenJumpPlus-Android/4.0.11 (Android 14/34/0/0)',
            'authorization': f'Bearer {self.token}',
            'x-giga-device-id': self.device_id,
        }

    def show_help(self):
        help_text = '''用法：
{0} {1}
{0} search QUERY
    搜索漫畫。QUERY為關鍵字
{0} list-chapter COMIC_ID
    列出漫畫章節。COMIC_ID為漫畫的ID
{0} dl [-o 下載位置] COMIC_ID CHAPTER_ID ...
    下載漫畫。COMIC_ID為漫畫的ID，CHAPTER_ID為章節的ID。可指定多個CHAPTER_ID
{0} dl-all [-o 下載位置] COMIC_ID ...
    下載漫畫所有章節。COMIC_ID為漫畫的ID。可指定多個COMIC_ID
{0} dl-seq [-o 下載位置] COMIC_ID ... INDEX
    依照章節序號下載漫畫。COMIC_ID為漫畫的ID，可指定多個COMIC_ID。INDEX為章節在list-chapter中的序號，序號前加r代表反序。也可使用-代表範圍。
'''
        print(help_text.format(sys.argv[0],
'''login GLSC
    在網頁版登錄，填入 glsc 這個 cookie'''))

    def getChapterList(self, comic_id):
        json_data = {
            'operationName': 'SeriesDetailEpisodeList',
            'variables': {
                'id': comic_id,
                'episodeOffset': 0,
                'episodeFirst': 1000,
                'episodeSort': 'NUMBER_ASC',
            },
            'query': 'query SeriesDetailEpisodeList($id: String!, $episodeOffset: Int = 0 , $episodeFirst: Int = 100 , $episodeSort: ReadableProductSorting = null ) { series(databaseId: $id) { __typename id databaseId publisherId title episodeDefaultSorting episodes: readableProducts(types: [EPISODE,SPECIAL_CONTENT], first: $episodeFirst, offset: $episodeOffset, sort: $episodeSort) { totalCount pageInfo { __typename ...ForwardPageInfo } edges { node { __typename id databaseId ...EpisodeListItem ...SpecialContentListItem } } } ...SeriesDetailBottomBanners } }  fragment ForwardPageInfo on PageInfo { hasNextPage endCursor }  fragment PurchaseInfo on PurchaseInfo { isFree hasPurchased hasPurchasedViaTicket purchasable purchasableViaTicket purchasableViaPaidPoint purchasableViaOnetimeFree unitPrice rentable rentalEndAt hasRented rentableByPaidPointOnly rentalTermMin }  fragment EpisodeIsViewed on Episode { id databaseId isViewed }  fragment EpisodeListItem on Episode { __typename id databaseId publisherId title subtitle thumbnailUriTemplate purchaseInfo { __typename ...PurchaseInfo } accessibility publishedAt isSakiyomi completeReadingInfo { visitorCanGetPoint gettablePoint } viewCount series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } ...EpisodeIsViewed }  fragment AnalyticsParameters on ReadableProduct { __typename id databaseId publisherId title ... on Episode { publishedAt series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } } ... on Volume { openAt series { id databaseId publisherId title } } ... on Ebook { publishedAt series { id databaseId publisherId title } } ... on Magazine { openAt magazineLabel { id databaseId publisherId title } } ... on SpecialContent { publishedAt series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } } }  fragment SpecialContentListItem on SpecialContent { __typename id databaseId publisherId title thumbnailUriTemplate purchaseInfo { __typename ...PurchaseInfo } accessibility publishedAt linkUrl series { id databaseId publisherId title serialUpdateScheduleLabel } ...AnalyticsParameters }  fragment SeriesDetailBottomBanners on Series { id databaseId bannerGroup(groupName: "series_detail_bottom") { __typename ... on ImageBanner { databaseId imageUriTemplate imageUrl linkUrl } ... on YouTubeBanner { videoId } } }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?SeriesDetailEpisodeList', headers=self.headers, json=json_data)
        j = response.json()
        chapters = j['data']['series']['episodes']['edges']
        ret = []
        for chapter in chapters:
            title = chapter['node']['title']
            subtitle = chapter['node'].get('subtitle')
            if subtitle:
                title = f'{title} {subtitle}'
            ret.append((chapter['node']['databaseId'], title, False))

        json_data = {
            'operationName': 'SeriesDetailVolumeList',
            'variables': {
                'id': comic_id,
                'volumeSort': 'NUMBER_ASC',
            },
            'query': 'query SeriesDetailVolumeList($id: String!, $volumeSort: ReadableProductSorting = NUMBER_DESC ) { series(databaseId: $id) { __typename id databaseId volumes: readableProducts(types: [VOLUME], first: 100, sort: $volumeSort) { __typename ...BookVolumeList } volumesBulkPurchaseItem: firstVolume { __typename id databaseId ...BookBulkPurchaseItem } volumeSeries { id publisherId title } hasEpisode: hasPublicReadableProduct(type: EPISODE) ...SeriesDetailBottomBanners } }  fragment ForwardPageInfo on PageInfo { hasNextPage endCursor }  fragment PurchaseInfo on PurchaseInfo { isFree hasPurchased hasPurchasedViaTicket purchasable purchasableViaTicket purchasableViaPaidPoint purchasableViaOnetimeFree unitPrice rentable rentalEndAt hasRented rentableByPaidPointOnly rentalTermMin }  fragment VolumeReadTrialAvailability on Volume { accessibility trialPageImages(first: 0) { totalCount } }  fragment AnalyticsParameters on ReadableProduct { __typename id databaseId publisherId title ... on Episode { publishedAt series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } } ... on Volume { openAt series { id databaseId publisherId title } } ... on Ebook { publishedAt series { id databaseId publisherId title } } ... on Magazine { openAt magazineLabel { id databaseId publisherId title } } ... on SpecialContent { publishedAt series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } } }  fragment BookListItem on ReadableProduct { __typename id publisherId databaseId title thumbnailUriTemplate purchaseInfo { __typename ...PurchaseInfo } accessibility ... on Volume { __typename description series { id databaseId } ...VolumeReadTrialAvailability } ... on Ebook { description series { id databaseId publisherId title } } ...AnalyticsParameters }  fragment BookVolumeList on ReadableProductConnection { pageInfo { __typename ...ForwardPageInfo } totalCount edges { node { __typename id databaseId ...BookListItem } } }  fragment BookBulkPurchaseItem on ReadableProduct { __typename id databaseId publisherId thumbnailUriTemplate title accessibility purchaseInfo { __typename ...PurchaseInfo } ... on Volume { number series { id databaseId volumeSeries { id databaseId title author { id databaseId name } } } } }  fragment SeriesDetailBottomBanners on Series { id databaseId bannerGroup(groupName: "series_detail_bottom") { __typename ... on ImageBanner { databaseId imageUriTemplate imageUrl linkUrl } ... on YouTubeBanner { videoId } } }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?SeriesDetailVolumeList', headers=self.headers, json=json_data)
        j = response.json()
        chapters = j['data']['series']['volumes']['edges']
        for chapter in chapters:
            ret.append((chapter['node']['databaseId'], chapter['node']['title'], False))

        return ret

    def downloadChapter(self, comic_id, chapter_id, root):
        comic_title, chapter_title, image_token, number = self.getChapterInfo(comic_id, chapter_id)
        if not comic_title:
            # Not episode, probably volume or special content
            self.downloadVolume(comic_id, chapter_id, root)
            return

        json_data = {
            'operationName': 'EpisodeViewerConditionallyCacheable',
            'variables': {
                'episodeID': chapter_id,
            },
            'query': 'query EpisodeViewerConditionallyCacheable($episodeID: String!) { episode(databaseId: $episodeID) { id databaseId pageImages { totalCount edges { node { src width height tshirtUrl clickableAreas { __typename ...ClickableArea } } } } purchaseInfo { __typename ...PurchaseInfo } } }  fragment ClickableArea on Clickable { __typename appUrl position { __typename ... on PageIndexReadableProductPosition { pageIndex: index } ... on CFIReadableProductPosition { cfi } } ... on ClickableRect { height left top width } }  fragment PurchaseInfo on PurchaseInfo { isFree hasPurchased hasPurchasedViaTicket purchasable purchasableViaTicket purchasableViaPaidPoint purchasableViaOnetimeFree unitPrice rentable rentalEndAt hasRented rentableByPaidPointOnly rentalTermMin }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?EpisodeViewerConditionallyCacheable', headers=self.headers, json=json_data)
        j = response.json()
        if not j['data']['episode']['pageImages']:
            if not j['data']['episode']['purchaseInfo']['purchasableViaOnetimeFree']:
                raise Exception(j['errors'][0]['message'])
            # Try unlocking chapter with one-time-free
            print('嘗試自動解鎖初回無料章節', chapter_title)
            json_data_one_time_free = {
                'operationName': 'ConsumeOnetimeFree',
                'variables': {
                    'input': {
                        'id': j['data']['episode']['id'],
                    },
                },
                'query': 'mutation ConsumeOnetimeFree($input: ConsumeOnetimeFreeInput!) { consumeOnetimeFree(input: $input) { isSuccess readableProduct { databaseId id accessibility purchaseInfo { __typename ...PurchaseInfo } } } }  fragment PurchaseInfo on PurchaseInfo { isFree hasPurchased hasPurchasedViaTicket purchasable purchasableViaTicket purchasableViaPaidPoint purchasableViaOnetimeFree unitPrice rentable rentalEndAt hasRented rentableByPaidPointOnly rentalTermMin }',
            }

            self.post_request('https://shonenjumpplus.com/api/v1/graphql?ConsumeOnetimeFree', headers=self.headers, json=json_data_one_time_free)
            # I am not checking response of this request, instead checking images availability
            response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?EpisodeViewerConditionallyCacheable', headers=self.headers, json=json_data)
            j = response.json()
            if not j['data']['episode']['pageImages']:
                raise Exception(j['errors'][0]['message'])
        image_download = ImageDownload(root, comic_title, f'{number} {chapter_title}')
        image_download.headers = {'X-GIGA-PAGE-IMAGE-AUTH': image_token}
        for i in j['data']['episode']['pageImages']['edges']:
            image_download.urls.append(i['node']['src'])
        self.download_list(image_download)

    def downloadVolume(self, comic_id, chapter_id, root):
        json_data = {
            'operationName': 'VolumeViewer',
            'variables': {
                'volumeID': chapter_id,
            },
            'query': 'query VolumeViewer($volumeID: String!) { volume(databaseId: $volumeID) { __typename id ...CommonVolumeViewer pageImages { totalCount edges { node { src width height tshirtUrl clickableAreas { __typename ...ClickableArea } } } } packedImage { url } tableOfContents { title position { index } } previous { __typename id databaseId purchaseInfo { __typename ...PurchaseInfo } ...ViewerLink } next { __typename id databaseId purchaseInfo { __typename ...PurchaseInfo } ...ViewerLink } viewHistory { __typename ...RemoteViewHistory } ...VolumeImprintPage ...CommonReadableProductViewer } }  fragment SpineItem on Spine { readingDirection startPosition }  fragment PurchaseInfo on PurchaseInfo { isFree hasPurchased hasPurchasedViaTicket purchasable purchasableViaTicket purchasableViaPaidPoint purchasableViaOnetimeFree unitPrice rentable rentalEndAt hasRented rentableByPaidPointOnly rentalTermMin }  fragment CommonVolumeViewer on Volume { id databaseId publisherId title permalink number pageImageToken thumbnailUri spine { __typename ...SpineItem } openAt closeAt series { id databaseId mylisted volumeSeries { id databaseId publisherId title author { id databaseId name } } } purchaseInfo { __typename ...PurchaseInfo } }  fragment ClickableArea on Clickable { __typename appUrl position { __typename ... on PageIndexReadableProductPosition { pageIndex: index } ... on CFIReadableProductPosition { cfi } } ... on ClickableRect { height left top width } }  fragment AnalyticsParameters on ReadableProduct { __typename id databaseId publisherId title ... on Episode { publishedAt series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } } ... on Volume { openAt series { id databaseId publisherId title } } ... on Ebook { publishedAt series { id databaseId publisherId title } } ... on Magazine { openAt magazineLabel { id databaseId publisherId title } } ... on SpecialContent { publishedAt series { id databaseId publisherId title serialUpdateScheduleLabel jamEpisodeWorkType } } }  fragment ViewerLink on ReadableProduct { __typename id databaseId purchaseInfo { __typename ...PurchaseInfo } accessibility ... on Episode { publisherId } ... on Magazine { publisherId } ... on Volume { publisherId } ...AnalyticsParameters }  fragment RemoteViewHistory on ReadableProductViewHistory { lastViewedAt lastViewedPosition { __typename ... on PageIndexReadableProductPosition { index } } }  fragment ImprintPageNextContent on ReadableProduct { __typename id databaseId title thumbnailUriTemplate accessibility purchaseInfo { __typename ...PurchaseInfo } ... on Magazine { isSubscribersOnly } ...AnalyticsParameters }  fragment VolumeImprintPage on Volume { id databaseId next { __typename id databaseId series { id databaseId } ...ImprintPageNextContent } }  fragment EpisodeShareContent on Episode { id databaseId title shareUrl permalink series { id databaseId title } }  fragment ReadableProductShareContent on ReadableProduct { __typename id databaseId ... on Ebook { title shareUrl } ... on Episode { __typename ...EpisodeShareContent } ... on Magazine { title permalink shareUrl } ... on Volume { title permalink shareUrl } }  fragment CommonReadableProductViewer on ReadableProduct { __typename id databaseId accessibility purchaseInfo { __typename ...PurchaseInfo } ... on Episode { id databaseId pageImages { totalCount } } ... on Magazine { id databaseId pageImages { totalCount } } ... on Volume { id databaseId pageImages { totalCount } } ...ReadableProductShareContent ...AnalyticsParameters }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?VolumeViewer', headers=self.headers, json=json_data)
        j = response.json()
        if not j['data']['volume']:
            # Not volume, probably special content
            raise Exception('不支持下載特別內容')

        comic_title = j['data']['volume']['series']['title']
        chapter_title = j['data']['volume']['title']
        number = str(j['data']['volume']['number']).zfill(2)
        image_download = ImageDownload(root, comic_title, f'Vol.{number} {chapter_title}')
        image_download.headers = {'X-GIGA-PAGE-IMAGE-AUTH': j['data']['volume']['pageImageToken']}
        if not j['data']['volume']['pageImages']:
            raise Exception(j['errors'][0]['message'])
        for i in j['data']['volume']['pageImages']['edges']:
            image_download.urls.append(i['node']['src'])
        self.download_list(image_download)

    def searchComic(self, query):
        json_data = {
            'operationName': 'SearchResult',
            'variables': {
                'keyword': query,
            },
            'query': 'query SearchResult($after: String, $keyword: String!) { search(after: $after, first: 50, keyword: $keyword, types: [SERIES,MAGAZINE_LABEL]) { pageInfo { __typename ...ForwardPageInfo } edges { node { __typename ...SearchResultItem } } } }  fragment ForwardPageInfo on PageInfo { hasNextPage endCursor }  fragment SerialInfoIcon on SerialInfo { isOriginal isIndies }  fragment SearchResultSeriesItem on Series { id databaseId thumbnailUriTemplate title author { id databaseId name } supportsOnetimeFree serialInfo { __typename ...SerialInfoIcon status } hasEpisode: hasPublicReadableProduct(type: EPISODE) hasEbook: hasPublicReadableProduct(type: EBOOK) hasVolume: hasPublicReadableProduct(type: VOLUME) hasSpecialContent: hasPublicReadableProduct(type: SPECIAL_CONTENT) readableProducts(first: 1, sort: NUMBER_DESC, types: [VOLUME,EBOOK]) { edges { node { id databaseId thumbnailUriTemplate } } } }  fragment SearchResultItem on ReadableProductParent { __typename ... on Series { __typename id publisherId seriesDatabaseId: databaseId ...SearchResultSeriesItem } ... on MagazineLabel { id magazineLabelDatabaseId: databaseId title publisherId latestIssue { id databaseId thumbnailUriTemplate } } }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?SearchResult', headers=self.headers, json=json_data)
        j = response.json()
        ret = []
        for i in j['data']['search']['edges']:
            ret.append((i['node']['seriesDatabaseId'], i['node']['title']))
        return ret

    def getChapterInfo(self, comic_id, chapter_id):
        json_data = {
            'operationName': 'EpisodeViewer',
            'variables': {
                'episodeID': chapter_id,
            },
            'query': 'query EpisodeViewer($episodeID: String!) { episode(databaseId: $episodeID) { id databaseId publisherId title number publishedAt pageImageToken spine { readingDirection startPosition } previousSpecialContent { id databaseId linkUrl } nextSpecialContent { id databaseId linkUrl } series { id databaseId publisherId title author { id databaseId name } serialUpdateScheduleLabel jamEpisodeWorkType openAt } } stampCard { __typename ...StampCardIcon } }  fragment StampCardIcon on StampCard { id databaseId iconImageUrl }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?EpisodeViewer', headers=self.headers, json=json_data)
        j = response.json()
        if not j['data']['episode']:
            # Not episode, probably volume or special content
            return None, None, None, None
        comic_title = j['data']['episode']['series']['title']
        chapter_title = j['data']['episode']['title']
        chapter_list = self.getChapterList(comic_id)
        for chapter in chapter_list:
            if chapter_id == chapter[0]:
                chapter_title = chapter[1]
                break
        image_token =  j['data']['episode']['pageImageToken']
        number = str(j['data']['episode']['number']).zfill(3)
        return comic_title, chapter_title, image_token, number

if __name__ == '__main__':
    Extractor().main()
