import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QSpinBox
from PySide6.QtCore import QSettings
from app.dashboard.modern_window import DashboardWindow
from app.dashboard.crafting_catalog import parse_recipes, reference_recipes, recipe_state
from app.dashboard.crafting_engine import CraftingWorker
from app.dashboard.job_queue import JobSpec
from PySide6.QtGui import QCloseEvent

class CraftingUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.settings_dir = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.settings_dir.name) / 'settings.ini'), QSettings.IniFormat)
        self.settings_patch = patch('app.dashboard.modern_window.QSettings', return_value=settings)
        self.settings_patch.start()
        self.window = DashboardWindow(Path(__file__).resolve().parents[2], connect_on_start=False)
    def tearDown(self):
        self.window.close(); self.window.deleteLater(); self.app.processEvents()
        self.settings_patch.stop()
        self.settings_dir.cleanup()
    def test_full_catalogue_and_editable_quantity_survive_filtering(self):
        data = {'craftingUnlocked':True, 'items':[
            {'DisplayName':'검증 무기', 'ProducedPerCraft':1, 'Craftable':True},
            {'DisplayName':'검증 재료', 'ProducedPerCraft':5, 'Craftable':False, 'Reason':'not_enough_ingredient'}]}
        self.window.apply_recipes(data)
        self.window.select_category('제작')
        self.window.search.setText('검증')
        self.assertEqual(self.window.catalog.rowCount(), 2)
        self.assertIsInstance(self.window.catalog.cellWidget(0,1), QSpinBox)
        self.window.catalog.cellWidget(0,1).setValue(17)
        self.window.search.setText('무기')
        self.assertEqual(self.window.catalog.rowCount(), 1)
        self.assertEqual(self.window.catalog.cellWidget(0,1).value(),17)
        self.window.add_job_key('craft:검증 무기')
        self.assertEqual(self.window.queue.jobs[0].spec.target_count,17)
        self.assertIsNone(self.window.queue.worker)
        self.window.search.setText('검증 무기')
        self.window.catalog.cellWidget(0,1).setValue(4)
        self.assertEqual(self.window.queue.jobs[0].spec.target_count,17)
    def test_offline_result_does_not_replace_previous_catalogue(self):
        self.window.apply_recipes({'items':[{'DisplayName':'검증 항목','ProducedPerCraft':1}]})
        self.window.apply_recipes({'pipe':'disconnected','reason':'game_off'})
        self.assertIn('검증 항목', self.window.recipe_rows)
    def test_overlay_option_and_matching_selected_category(self):
        self.window.select_category('무한가공소')
        self.assertTrue(self.window.category_buttons['무한가공소'].isChecked())
        self.window.toggle_overlay(False)
        self.assertFalse(self.window.overlay.enabled)
        self.assertEqual(self.window.overlay.width(),240)

    def test_toolbar_and_queue_options_control_one_borderless_overlay(self):
        self.window.overlay_button.setChecked(False)
        self.assertFalse(self.window.overlay_toggle.isChecked())
        self.assertFalse(self.window.overlay.enabled)
        self.assertFalse(self.window.environment_overlay.enabled)
        self.window.overlay_toggle.setChecked(True)
        self.assertTrue(self.window.overlay_button.isChecked())
        self.assertTrue(self.window.overlay.enabled)
        self.assertTrue(self.window.environment_overlay.enabled)
        self.assertFalse(self.window.environment_overlay.polling_allowed)
        self.assertFalse(hasattr(self.window, 'overlay_manager'))

    def test_scroll_jobs_still_resolve_after_live_catalogue_replaces_equipment_rows(self):
        self.window.apply_recipes({'items':[{'DisplayName':'검증 항목','ProducedPerCraft':1,'Craftable':True}]})
        self.assertFalse(any(spec.key.startswith('equipment_') for spec in self.window.specs))
        self.window._on_scrolls_loaded([{'DisplayName':'제작 스크롤: 크레센트 엣지소드',
                                        'Count':3, 'Location':'inventory'}])
        [job] = self.window.queue.jobs
        self.assertEqual(job.spec.make_worker().recipe, '크레센트 엣지소드')
        self.assertEqual(job.spec.make_worker().remaining, 2)
        self.assertEqual(job.repeats, 3)

    def test_workshop_overlay_uses_current_upstream_family_target(self):
        from app.dashboard.altering_routine import FAMILIES
        metal = next(family for family in FAMILIES if family.key == 'metal')
        self.window.routine._controls['metal']._slider.setValue(0)
        self.window.queue.on_routine_snapshot({'queue':{'metal':7}, 'queue_completed':{'metal':2}})
        [row] = [entry for entry in self.window.queue.last_progress['materials']
                 if entry['name'] == metal.tiers[0].name]
        self.assertEqual((row['owned'], row['required']), (2,7))

    def test_environment_request_is_included_in_busy_and_close_guards(self):
        from unittest.mock import Mock
        worker = Mock()
        worker.isRunning.return_value = True
        self.window.environment_overlay.worker = worker
        try:
            self.assertTrue(self.window.query_busy())
            event = QCloseEvent()
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertFalse(self.window.environment_overlay.enabled)
        finally:
            self.window.environment_overlay.worker = None
    def test_duplicate_recipe_is_not_silently_discarded(self):
        rows = parse_recipes({'items':[
            {'DisplayName':'최상급 붕대','ProducedPerCraft':10,'Craftable':True},
            {'DisplayName':'최상급 붕대','ProducedPerCraft':5,'Craftable':True},
            {'DisplayName':'회복 물약','ProducedPerCraft':5,'Craftable':True}]})
        self.assertEqual(set(rows), {'최상급 붕대','회복 물약'})
        self.assertEqual(rows['최상급 붕대']['_catalog_variant_count'],2)
        self.assertEqual([v['ProducedPerCraft'] for v in rows['최상급 붕대']['_catalog_variants']],[10,5])
        self.assertIn(rows['최상급 붕대']['ProducedPerCraft'],(10,5))
        self.assertTrue(rows['최상급 붕대']['Craftable'])
        self.assertEqual(recipe_state(rows['최상급 붕대']),'동명 제작법 2종 · 자동 선택')
        self.assertEqual(recipe_state(rows['회복 물약']),'제작 가능')

    def test_duplicate_catalogue_representative_prefers_currently_ready_recipe(self):
        rows = parse_recipes({'items':[
            {'DisplayName':'시험 물약','ProducedPerCraft':10,'Craftable':False,
             'Reason':'not_enough_ingredient',
             'MissingIngredients':[{'DisplayName':'시험 약초','Required':8,'Owned':0}]},
            {'DisplayName':'시험 물약','ProducedPerCraft':5,'Craftable':True}]})
        self.assertTrue(rows['시험 물약']['Craftable'])
        self.assertEqual(rows['시험 물약']['ProducedPerCraft'],5)
        self.assertEqual(rows['시험 물약']['_catalog_variant_count'],2)
        self.assertEqual(rows['시험 물약']['_catalog_variants'][0]['MissingIngredients'][0]['Required'],8)

    def test_identical_repeated_rows_are_one_actionable_recipe(self):
        row = {'DisplayName':'회복 물약','ProducedPerCraft':5,'Craftable':True}
        rows = parse_recipes({'items':[dict(row),dict(row)]})
        self.assertEqual(rows['회복 물약']['_catalog_variant_count'],1)
        self.assertEqual(recipe_state(rows['회복 물약']),'제작 가능')

    def test_requested_consumables_are_visible_before_connection(self):
        self.window.select_category('제작')
        names = {self.window.catalog.item(i,0).text() for i in range(self.window.catalog.rowCount())}
        expected = {'회복 물약','상급 자동회복 물약','치명타 비약','염색약','짜먹는 간식',
                    '마법 유탄 부품','화염 마법 유탄','못','전문 캠프파이어 키트',
                    '낚시 애호가 소환 의자 상자(핑크)','갈색 닭 변신 인형','곰 변신 인형'}
        self.assertTrue(expected <= names)
        self.assertEqual(len(reference_recipes()),96)
        self.assertTrue(set(reference_recipes()) <= names)
        self.assertTrue(all('MissingIngredients' not in r for r in reference_recipes().values()))
        self.window.search.setText('회복 물약')
        self.window.add_job_key('craft:회복 물약')
        self.assertEqual(self.window.queue.jobs[0].spec.target_count,5)
        self.assertIsNone(self.window.queue.worker)

    def test_live_duplicates_do_not_block_requested_names_or_quantity(self):
        self.window.apply_recipes({'items':[
            {'DisplayName':'최상급 붕대','ProducedPerCraft':10,'Craftable':True},
            {'DisplayName':'최상급 붕대','ProducedPerCraft':5,'Craftable':False},
            {'DisplayName':'회복 물약','ProducedPerCraft':5,'Craftable':True}]})
        self.window.select_category('제작')
        self.assertEqual(self.window.catalog.rowCount(),96)
        self.assertTrue(self.window.catalog_loaded)
        self.window.search.setText('최상급 붕대')
        self.assertEqual(self.window.catalog.rowCount(),1)
        self.assertEqual(self.window.catalog.item(0,2).text(),'동명 제작법 2종 · 자동 선택')
        self.assertEqual(self.window.catalog.cellWidget(0,1).singleStep(),10)
        with patch.object(self.window.craft_detail, 'show_progress') as detail:
            self.window.catalog.setCurrentCell(0,0)
            self.window.show_recipe_detail()
        message = detail.call_args.args[0]['message']
        self.assertIn('재료 준비량을 비교해 자동 선택',message)
        self.assertIn('이름으로 제작을 요청',message)
        self.assertIn('실제 생산 결과를 확인',message)
        self.assertNotIn('자동 실행을 멈추고',message)
        self.window.search.setText('회복 물약')
        self.assertEqual(self.window.catalog.cellWidget(0,1).singleStep(),5)
        self.window.catalog.cellWidget(0,1).setValue(20)
        self.window.add_job_key('craft:회복 물약')
        self.assertEqual(self.window.queue.jobs[0].spec.target_count,20)

    def test_unique_live_spacing_match_uses_exact_game_command_name(self):
        self.window.apply_recipes({'items':[{'DisplayName':'회복물약','ProducedPerCraft':5,'Craftable':True}]})
        self.assertNotIn('회복 물약',self.window.recipe_rows)
        self.assertEqual(self.window.recipe_rows['회복물약']['_catalog_group'],'회복')
        self.window.add_job_key('craft:회복물약')
        self.assertEqual(self.window.queue.jobs[0].spec.recipe_name,'회복물약')

    def test_close_request_keeps_incomplete_crafting_checkpoint(self):
        worker = CraftingWorker('검증 무기', 3)
        worker.checkpoint['completed'] = 1
        worker.remaining = 2
        queue = self.window.queue
        queue.add(JobSpec('craft:검증 무기', '검증 무기', lambda:worker, 3, '검증 무기'))
        queue.worker = worker
        with patch.object(worker, 'isRunning', return_value=True):
            event = QCloseEvent()
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
        self.assertTrue(worker._stop_requested)
        queue.on_finished()
        self.assertEqual(len(queue.jobs), 1)
        self.assertEqual(queue.jobs[0].craft_checkpoint['completed'], 1)
        with patch.object(CraftingWorker, 'start'):
            queue.toggle_pause()
        self.assertEqual(queue.worker.checkpoint['completed'], 1)
        queue.interrupted = True
        queue.on_finished()

    def test_query_worker_blocks_music_queue_and_duplicate_catalogue_sync(self):
        with patch.object(self.window, 'query_busy', return_value=True), patch('app.dashboard.modern_window.RecipeCatalogWorker') as factory:
            self.assertTrue(self.window.music_panel.guard())
            self.assertTrue(self.window.queue.activity_guard())
            self.window.sync_recipes()
            factory.assert_not_called()

    def test_documented_response_envelope_and_bad_rows(self):
        parsed = parse_recipes({'status':'accepted','body':{'items':[{'DisplayName':'검증 항목'}]}})
        self.assertIn('검증 항목', parsed)
        with self.assertRaises(ValueError): parse_recipes({'items':[None]})

if __name__ == '__main__': unittest.main()
