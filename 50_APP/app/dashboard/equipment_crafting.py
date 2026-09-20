"""Equipment jobs use live recipes and retain unfinished output counts.

Each equipment recipe is bought from a town's 임무 게시판 NPC as a "제작 스크롤: <이름>"
quest item, and one scroll's weekly quota is exactly 2 of that equipment - which is why
the default target below is 2, not an arbitrary round number (user, 2026-09-20).
"""
from .recipe_cooking import RecipeCookingWorker, CookingError

EQUIPMENT_RECIPES = (
    '두꺼운 전투복 신발', '사슬 갑옷 신발', '두꺼운 가죽 갑옷 신발',
    '크레센트 엣지소드', '그랜드 크로스보우', '로터스 힐링 완드',
    '가죽 갑옷 신발S', '전투복 신발S', '비늘 갑옷 신발S',
    '론 엣지소드S', '라이트 크로스보우S', '마블 힐링 완드S',
)

# Town -> the 3 equipment recipes its 임무 게시판 NPC sells scrolls for (user, 2026-09-20).
TOWN_EQUIPMENT = {
    '던바튼': ('크레센트 엣지소드', '그랜드 크로스보우', '로터스 힐링 완드'),
    '콜헨': ('두꺼운 전투복 신발', '사슬 갑옷 신발', '두꺼운 가죽 갑옷 신발'),
    '반호르': ('론 엣지소드S', '라이트 크로스보우S', '마블 힐링 완드S'),
    '이멘마하': ('가죽 갑옷 신발S', '전투복 신발S', '비늘 갑옷 신발S'),
}

class EquipmentCraftWorker(RecipeCookingWorker):
    def __init__(self, recipe, count=2):
        super().__init__(recipe, count)

    def recipe_info(self, name):
        recipe = super().recipe_info(name)
        if name == self.recipe:
            produced = recipe.get('ProducedPerCraft')
            if not isinstance(produced, int) or produced <= 0 or self.remaining % produced:
                raise CookingError(f'{name}: 1회 생산량으로 남은 {self.remaining}개를 정확히 제작할 수 없습니다.')
        return recipe
