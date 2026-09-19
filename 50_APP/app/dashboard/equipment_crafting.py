"""Equipment jobs use live recipes and retain unfinished output counts."""
from .recipe_cooking import RecipeCookingWorker, CookingError

EQUIPMENT_RECIPES = (
    '두꺼운 전투복 신발', '사슬 갑옷 신발', '두꺼운 가죽 갑옷 신발',
    '크레센트 엣지소드', '그랜드 크로스보우', '로터스 힐링 완드',
    '가죽 갑옷 신발S', '전투복 신발S', '비늘 갑옷 신발S',
    '론 엣지 소드S', '라이트 크로스보우S', '마블 힐링 완드S',
)

class EquipmentCraftWorker(RecipeCookingWorker):
    def __init__(self, recipe):
        super().__init__(recipe, 2)

    def recipe_info(self, name):
        recipe = super().recipe_info(name)
        if name == self.recipe:
            produced = recipe.get('ProducedPerCraft')
            if not isinstance(produced, int) or produced <= 0 or self.remaining % produced:
                raise CookingError(f'{name}: 1회 생산량으로 남은 {self.remaining}개를 정확히 제작할 수 없습니다.')
        return recipe
