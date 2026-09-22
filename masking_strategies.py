"""마스킹 표기 방식 4종.

- token: 기존 방식. `[PII_PERSON_1]`처럼 라벨+순번으로 표기.
- symbol: 법원 판결문/공문서에서 흔히 쓰는 방식. 문자를 ○로 치환하되
  구분 기호(-, ., @, /, 공백 등)는 유지해 형태만 남긴다.
- pseudonym: 그럴듯한 가짜 값으로 치환한다. 같은 원문은 문서 내에서
  항상 같은 가명으로 치환되어(캐시), 문맥상 동일 인물/값임을 알아볼
  수 있으면서도 실제 값은 드러나지 않는다.
- redact: 완전 마스킹. 원문 길이·형태와 무관하게 `[REDACTED]`로 치환해
  정보를 전혀 남기지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MaskStyle(str, Enum):
    TOKEN = "token"
    SYMBOL = "symbol"
    PSEUDONYM = "pseudonym"
    REDACT = "redact"


@dataclass(frozen=True)
class StyleOption:
    id: str
    title: str
    description: str
    example: str


STYLE_OPTIONS: tuple[StyleOption, ...] = (
    StyleOption(
        MaskStyle.TOKEN.value,
        "토큰 표기",
        "라벨+순번으로 표기",
        "[PII_PERSON_1]",
    ),
    StyleOption(
        MaskStyle.SYMBOL.value,
        "특수기호 (법원식)",
        "글자를 ○로 치환, 구분 기호는 유지",
        "○○○",
    ),
    StyleOption(
        MaskStyle.PSEUDONYM.value,
        "가명 치환",
        "그럴듯한 가짜 값으로 치환, 동일 원문은 동일 가명 유지",
        "김도윤",
    ),
    StyleOption(
        MaskStyle.REDACT.value,
        "완전 마스킹",
        "형태·길이 정보 없이 전부 가림",
        "[REDACTED]",
    ),
)

_KEEP_CHARS = set("-./@() 　")

_PSEUDONYM_POOL_PERSON = (
    "김도윤", "이서연", "박하람", "최지훈", "정은우",
    "한소율", "오태경", "장미래", "임가온", "신유담",
)
_PSEUDONYM_POOL_ADDRESS = (
    "서울특별시 중구 세종대로 100",
    "부산광역시 동래구 충렬대로 120",
    "대구광역시 중구 동성로 45",
    "인천광역시 미추홀구 인주대로 200",
    "광주광역시 동구 금남로 10",
)


def _symbol_replace(text: str) -> str:
    return "".join(ch if ch in _KEEP_CHARS else "○" for ch in text)


def _build_pseudonym(label: str, index: int) -> str:
    if label == "private_person":
        return _PSEUDONYM_POOL_PERSON[(index - 1) % len(_PSEUDONYM_POOL_PERSON)]
    if label == "private_address":
        return _PSEUDONYM_POOL_ADDRESS[(index - 1) % len(_PSEUDONYM_POOL_ADDRESS)]
    if label == "private_phone":
        return f"010-{1000 + index:04d}-{2000 + index:04d}"
    if label == "private_email":
        return f"user{index}@masked-example.com"
    if label == "private_url":
        return f"masked-site-{index}.example.com"
    if label == "account_number":
        return f"000-{index:03d}-{100000 + index:06d}"
    if label == "secret":
        return f"REDACTED-KEY-{index:04d}"
    return f"MASKED-{index}"


class ReplacementBuilder:
    """마스킹 치환 문자열을 생성하는 상태 저장기.

    토큰/가명 방식은 라벨별 순번 카운터가, 가명 방식은 원문→가명
    캐시가 필요해서 한 번의 분석(요청) 동안 상태를 들고 있는다.
    """

    def __init__(self, style: str | MaskStyle):
        self.style = MaskStyle(style)
        self._token_counters: dict[str, int] = {}
        self._pseudonym_counters: dict[str, int] = {}
        self._pseudonym_cache: dict[tuple[str, str], str] = {}

    def replacement_for(self, label: str, original: str) -> str:
        if self.style is MaskStyle.TOKEN:
            stem = label.removeprefix("private_").upper()
            key = f"PII_{stem}"
            self._token_counters[key] = self._token_counters.get(key, 0) + 1
            return f"[{key}_{self._token_counters[key]}]"

        if self.style is MaskStyle.SYMBOL:
            return _symbol_replace(original)

        if self.style is MaskStyle.REDACT:
            return "[REDACTED]"

        # PSEUDONYM
        cache_key = (label, original.strip().lower())
        if cache_key in self._pseudonym_cache:
            return self._pseudonym_cache[cache_key]
        self._pseudonym_counters[label] = self._pseudonym_counters.get(label, 0) + 1
        value = _build_pseudonym(label, self._pseudonym_counters[label])
        self._pseudonym_cache[cache_key] = value
        return value
