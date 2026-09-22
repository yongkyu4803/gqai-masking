"""마스킹 표기 방식 4종.

- token: 기존 방식. `[PII_PERSON_1]`처럼 라벨+순번으로 표기.
- court: 대법원 「판결서 등의 열람 및 복사를 위한 비실명 처리 기준」
  (재일 2014-2)을 따른 방식. 제5조①(성명 → 알파벳 대문자),
  제7조(주소의 시·군·구 이후 → 알파벳 대문자), 제8조①(계좌번호 등
  식별 숫자 → 고유 알파벳 대문자), 제8조②(주민등록번호 → 완전 삭제)
  에 근거한다. "○○○" 표기는 언론 등에서 쓰는 관행일 뿐 이 예규의
  공식 표기가 아니므로 사용하지 않는다.
- pseudonym: 그럴듯한 가짜 값으로 치환한다. 같은 원문은 문서 내에서
  항상 같은 가명으로 치환되어(캐시), 문맥상 동일 인물/값임을 알아볼
  수 있으면서도 실제 값은 드러나지 않는다.
- redact: 완전 마스킹. 원문 길이·형태와 무관하게 `[REDACTED]`로 치환해
  정보를 전혀 남기지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class MaskStyle(str, Enum):
    TOKEN = "token"
    COURT = "court"
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
        MaskStyle.COURT.value,
        "법원식 (비실명 처리 예규)",
        "고유 알파벳 대문자 부여(A, B, C...), 주민등록번호는 완전 삭제",
        "A",
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

# 주민등록번호 형식(예: 850205-1234567). 라벨과 무관하게 값 자체가
# 이 형태와 일치하면 예규 제8조②에 따라 완전 삭제한다.
_RRN_PATTERN = re.compile(r"^\d{6}-[1-4]\d{6}$")


def _next_letter(index: int) -> str:
    """1→A, 2→B, ..., 26→Z, 27→AA, 28→AB... (엑셀 열 이름과 동일한 규칙)."""
    letters = []
    n = index
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


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
        self._court_cache: dict[str, str] = {}
        self._court_next_index = 1

    def replacement_for(self, label: str, original: str) -> str:
        if self.style is MaskStyle.TOKEN:
            stem = label.removeprefix("private_").upper()
            key = f"PII_{stem}"
            self._token_counters[key] = self._token_counters.get(key, 0) + 1
            return f"[{key}_{self._token_counters[key]}]"

        if self.style is MaskStyle.COURT:
            # 제8조②: 주민등록번호 형식은 완전 삭제
            if _RRN_PATTERN.match(original.strip()):
                return ""
            # 제5조①/제7조/제8조①: 값마다 고유 알파벳 대문자, 동일 원문 재사용
            cache_key = original.strip().lower()
            if cache_key in self._court_cache:
                return self._court_cache[cache_key]
            letter = _next_letter(self._court_next_index)
            self._court_next_index += 1
            self._court_cache[cache_key] = letter
            return letter

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
