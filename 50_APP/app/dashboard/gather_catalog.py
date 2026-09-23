"""Offline gathering references and read-only official connector synchronization."""
import json
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from ..cli_client import run_cli
from .crafting_engine import unpack, failure

# Fishing starts an indefinite action, so it cannot use the one-shot gather queue.
FISHING_ITEMS = set('농어|메기|연어|은어|잡어|고등어|금린어|은붕어|갈색송어|참사랑어|초롱아귀|파이크퍼치|민물꼬치고기|어둠유령고기|얼룩덜룩한 옷감|브리흐네 잉어|으스러진 신상 조각|망가진 신발|망가진 옷감|무지개 송어|사령의 구슬|빛바랜 기도문|춤추는 꽃가지|훼손된 계약서|변이된 물보라초|부러진 악몽의 검|도금이 벗겨진 장식|오래된 발톱 화석|축축한 편지 뭉치|기이한 검은 물고기|황금 농어|황금 메기|황금 송어|황금 연어|황금 잉어|검은 물고기|이끼 덩어리|황금 민물꼬치고기|깨진 성화 목판|보석 빠진 반지|윤이 나는 천 조각|이끼 낀 쇳조각|용 석상 스케치'.split('|'))


def reference_gather_items():
    path = Path(__file__).parent / 'assets' / 'gather_items_reference.json'
    return sorted({row['name'] for row in json.loads(path.read_text(encoding='utf-8'))['items']})


def parse_gather_items(data):
    data = unpack(data)
    if failure(data):
        raise ValueError('게임에 접속하고 AI 커넥터를 켠 뒤 다시 동기화해주세요.')
    rows = data if isinstance(data, list) else data.get('items') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('채집 목록을 읽지 못했습니다. 게임 연결을 확인해주세요.')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('DisplayName'), str) or not row['DisplayName'].strip():
            raise ValueError('채집 목록 응답 형식을 확인할 수 없습니다.')
        if row['DisplayName'] not in FISHING_ITEMS:
            result[row['DisplayName']] = dict(row)
    return result


def gather_state(name, live):
    if live is None:
        return '조건 확인 전'
    if name not in live:
        return '현재 목록에 없음'
    if live[name].get('ToolOk') is False:
        return '도구 확인 필요'
    return '채집 가능' if live[name].get('ToolOk') is True else '게임 목록 확인'


class GatherCatalogWorker(QThread):
    result = Signal(object)

    def run(self):
        self.result.emit(run_cli('get_gatherable_items', timeout=30))
