import hashlib
import sys

from extractorbase import *


class Extractor(ExtractorBase):
    name = 'jumpplus'

    def __init__(self):
        super().__init__()
        self.device_id = hashlib.md5(self.token.encode()).hexdigest()[:16]
        self.headers = {
            # x-giga-device-id required for 初回無料
            'user-agent': 'ShonenJumpPlus-Android/4.0.18 (Android 14/34/0/0)',
            'authorization': f'Bearer {self.token}',
            'x-giga-device-id': self.device_id,
        }

    def show_help(self):
        print(self.help_text_with_bought.format(sys.argv[0],
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
        if not 'data' in j:
            raise Exception(j['message'])
        chapters = j['data']['series']['episodes']['edges']
        ret = []
        for chapter in chapters:
            title = chapter['node']['title']
            subtitle = chapter['node'].get('subtitle')
            if subtitle:
                title = f'{title} {subtitle}'
            # Note: Chapters recently unlocked with one time free can be downloaded,
            # but I do not find a way to detect them. They are displayed as locked.
            locked_status = self.getLockedStatus(chapter['node']['purchaseInfo'])
            ret.append((chapter['node']['databaseId'], title, locked_status))

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
            locked_status = self.getLockedStatus(chapter['node']['purchaseInfo'])
            ret.append((chapter['node']['databaseId'], chapter['node']['title'], locked_status))

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

    def getBoughtComicList(self):
        json_data = {
            'operationName': 'BookshelfPurchasedShelfByType',
            'variables': {
                'type': 'VOLUME',
                'sort': 'PURCHASED_AT_DESC',
            },
            'query': 'query BookshelfPurchasedShelfByType($type: ReadableProductType!, $after: String, $first: Int! = 30 , $sort: PurchasedReadableProductParentSorting! = VIEWED_AT_DESC ) { userAccount { databaseId isLoggedIn purchasedReadableProductParents(type: $type, first: $first, after: $after, sort: $sort) { pageInfo { __typename ...ForwardPageInfo } edges { node { __typename id ...BookshelfReadableProductParentItem latestPurchasedReadableProduct: purchasedReadableProducts(first: 1, sort: NUMBER_DESC, type: $type) { edges { node { id databaseId thumbnailUriTemplate } } } } } } } }  fragment ForwardPageInfo on PageInfo { hasNextPage endCursor }  fragment BookshelfReadableProductParentItem on ReadableProductParent { __typename ... on MagazineLabel { id magazineLabelDatabaseId: databaseId title } ... on Series { id seriesDatabaseId: databaseId thumbnailUriTemplate author { id databaseId name } volumeSeries { id databaseId title } } }',
        }

        response = self.post_request('https://shonenjumpplus.com/api/v1/graphql?opname=BookshelfPurchasedShelfByType', headers=self.headers, json=json_data)
        j = response.json()
        if not 'data' in j:
            raise Exception(j['message'])
        ret = []
        for i in j['data']['userAccount']['purchasedReadableProductParents']['edges']:
            ret.append((i['node']['seriesDatabaseId'], i['node']['volumeSeries']['title']))
        return ret

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
        if not 'data' in j:
            raise Exception(j['message'])
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

    def getLockedStatus(self, purchase_info):
        locked_status = LockedStatus.locked
        if purchase_info['isFree']:
            locked_status = LockedStatus.free
        elif purchase_info['hasRented']:
            locked_status = LockedStatus.temp_unlocked
        elif purchase_info['hasPurchased']:
            locked_status = LockedStatus.unlocked
        return locked_status

if __name__ == '__main__':
    Extractor().main()
