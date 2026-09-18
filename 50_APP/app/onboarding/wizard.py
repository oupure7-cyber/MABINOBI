"""First-run onboarding wizard: walks a new user through everything 40_ONBOARDING/
01_사용자_설치_가이드.md describes, with real checks where the environment allows it
(Node/Claude Code/Python/mcp package/game connector) and manual steps where it can't
be automated (account login, subscription - both need a browser/interactive session).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from . import checks
from ..proc_utils import open_terminal, open_url

CheckFn = Callable[[], tuple[bool, str]]


class CheckPage(QWizardPage):
    """A page listing one or more automatic checks plus optional action buttons."""

    def __init__(
        self,
        title: str,
        intro_html: str,
        items: list[tuple[str, CheckFn]],
        actions: list[tuple[str, Callable[[], None]]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setTitle(title)
        self._items = items
        self._status_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout()

        intro = QLabel(intro_html)
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        layout.addWidget(intro)

        for name, _fn in items:
            label = QLabel(f"⏳ {name}: 확인 중...")
            label.setWordWrap(True)
            self._status_labels[name] = label
            layout.addWidget(label)

        button_row = QHBoxLayout()
        recheck = QPushButton("다시 확인")
        recheck.clicked.connect(self.run_checks)
        button_row.addWidget(recheck)
        for label_text, callback in actions or []:
            btn = QPushButton(label_text)
            btn.clicked.connect(callback)
            button_row.addWidget(btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        layout.addStretch(1)

        self.setLayout(layout)

    def initializePage(self) -> None:
        self.run_checks()

    def run_checks(self) -> None:
        for name, fn in self._items:
            try:
                ok, detail = fn()
            except Exception as exc:  # noqa: BLE001 - surface any check failure, don't crash the wizard
                ok, detail = False, f"확인 중 오류: {exc}"
            icon = "✅" if ok else "⚠️"
            self._status_labels[name].setText(f"{icon} {name}: {detail}")


class WelcomePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("마비노비에 오신 것을 환영합니다")
        label = QLabel(
            "이 마법사는 넥슨 공식 <b>AI 커넥터</b>와 연동하기 위해 필요한 준비 과정을 "
            "안내합니다.<br><br>"
            "1. Claude Code 설치<br>"
            "2. Claude 계정 로그인<br>"
            "3. 구독/결제 연결<br>"
            "4. Python 및 MCP 서버 준비<br>"
            "5. 이 프로젝트를 Claude Code에 연결<br>"
            "6. 게임 내 AI 커넥터 옵션 켜기<br><br>"
            "각 단계는 건너뛰어도 되며, 나중에 메뉴에서 다시 열 수 있습니다."
        )
        label.setWordWrap(True)
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)


class FinishPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("준비 완료")
        label = QLabel(
            "여기까지 마쳤다면 대시보드로 이동할 준비가 된 것입니다.<br>"
            "일부 항목에 ⚠️가 남아있어도 나중에 메뉴 → '설치 마법사 다시 열기'로 언제든 돌아올 수 있습니다."
        )
        label.setWordWrap(True)
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)


class OnboardingWizard(QWizard):
    skipped = Signal()

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.setWindowTitle("초기 설정 마법사")
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.HaveCustomButton1, True)
        self.setButtonText(QWizard.CustomButton1, "나중에 하기 (건너뛰기)")
        self.setButtonLayout(
            [
                QWizard.CustomButton1,
                QWizard.Stretch,
                QWizard.BackButton,
                QWizard.NextButton,
                QWizard.FinishButton,
                QWizard.CancelButton,
            ]
        )
        self.customButtonClicked.connect(self._on_skip)

        self.addPage(WelcomePage())
        self.addPage(self._node_claude_page())
        self.addPage(self._account_page())
        self.addPage(self._subscription_page())
        self.addPage(self._python_mcp_page())
        self.addPage(self._connect_project_page())
        self.addPage(self._game_connector_page())
        self.addPage(FinishPage())

        self.resize(640, 480)

    # -- pages ---------------------------------------------------------

    def _node_claude_page(self) -> CheckPage:
        return CheckPage(
            title="1. Claude Code 설치",
            intro_html=(
                "Claude Code는 터미널에서 Claude AI를 실행하는 CLI 도구로, Node.js가 필요합니다.<br>"
                "설치되어 있지 않다면 아래 버튼으로 설치 창을 열 수 있습니다."
            ),
            items=[("Node.js", checks.check_node), ("Claude Code", checks.check_claude_code)],
            actions=[
                ("nodejs.org 열기", lambda: open_url("https://nodejs.org")),
                (
                    "Claude Code 설치 (터미널 열기)",
                    lambda: open_terminal("npm install -g @anthropic-ai/claude-code"),
                ),
            ],
        )

    def _account_page(self) -> CheckPage:
        return CheckPage(
            title="2. Claude 계정 로그인",
            intro_html=(
                "claude.ai 계정이 없다면 먼저 가입하세요. 계정이 있다면 아래 버튼으로 터미널에서 "
                "<code>claude</code>를 실행해 로그인을 진행할 수 있습니다 (브라우저 인증)."
            ),
            items=[("Claude Code", checks.check_claude_code)],
            actions=[
                ("claude.ai 열기", lambda: open_url("https://claude.ai")),
                ("claude 로그인 실행 (터미널 열기)", lambda: open_terminal("claude")),
            ],
        )

    def _subscription_page(self) -> CheckPage:
        return CheckPage(
            title="3. 구독/결제 연결",
            intro_html=(
                "무료 계정은 사용량 제한이 있어, 반복적인 자동화 요청에는 <b>Claude Pro/Max 구독</b> "
                "또는 <b>API 종량 결제</b>가 필요합니다. 이 비용은 마비노기 모바일과 무관하게 "
                "Anthropic에 직접 지불하는 비용입니다.<br>"
                "이 항목은 자동으로 확인할 수 없으니, 아래에서 직접 연결 여부를 확인해 주세요."
            ),
            items=[],
            actions=[
                ("claude.ai/upgrade 열기 (Pro/Max 구독)", lambda: open_url("https://claude.ai/upgrade")),
                ("console.anthropic.com 열기 (API 결제)", lambda: open_url("https://console.anthropic.com")),
            ],
        )

    def _python_mcp_page(self) -> CheckPage:
        def install():
            checks.install_mcp_package(self.project_root)

        return CheckPage(
            title="4. Python 및 MCP 서버 준비",
            intro_html=(
                "이 프로젝트의 MCP 서버는 Python으로 작성되어 있습니다. Python이 없다면 먼저 설치하고, "
                "있다면 아래 버튼으로 MCP 서버에 필요한 패키지를 설치할 수 있습니다."
            ),
            items=[("Python", checks.check_python), ("mcp 패키지", checks.check_mcp_package)],
            actions=[
                ("python.org 열기", lambda: open_url("https://www.python.org/downloads/")),
                ("mcp 패키지 설치", install),
            ],
        )

    def _connect_project_page(self) -> CheckPage:
        def auto_configure():
            checks.write_mcp_json(self.project_root)

        return CheckPage(
            title="5. 이 프로젝트를 Claude Code에 연결",
            intro_html=(
                f"프로젝트 경로: <code>{self.project_root}</code><br>"
                "이 PC에서 처음 여는 것이라면 아래 '자동 설정' 버튼으로 <code>.mcp.json</code>에 "
                "이 PC의 Python 경로를 등록할 수 있습니다. 이후 Claude Code로 이 폴더를 열면 "
                "MCP 서버가 자동으로 인식됩니다 (최초 1회 승인 필요)."
            ),
            items=[("MCP 서버 등록 상태", lambda: checks.mcp_json_status(self.project_root))],
            actions=[
                ("이 PC용으로 자동 설정", auto_configure),
                (
                    "Claude Code 열기 (터미널)",
                    lambda: open_terminal("claude", cwd=str(self.project_root)),
                ),
            ],
        )

    def _game_connector_page(self) -> CheckPage:
        return CheckPage(
            title="6. 게임 내 AI 커넥터 옵션 켜기",
            intro_html=(
                "마비노기 모바일 PC 버전에서 [메뉴(≡)] → [환경설정] → [게임] → [AI 제어]를 켜고 "
                "이용 확인 팝업에서 [활성화]를 눌러주세요. 활성화 후 7일간 미사용 시 자동으로 꺼집니다.<br>"
                "게임이 실행 중이어야 아래 확인이 성공합니다."
            ),
            items=[("게임 연결 상태", checks.check_game_connector)],
        )

    # -- skip handling ---------------------------------------------------

    def _on_skip(self, which) -> None:
        if which == QWizard.CustomButton1:
            self.skipped.emit()
            self.reject()
