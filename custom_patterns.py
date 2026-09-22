"""모델이 놓치는 PII를 잡기 위한 보조 탐지기.

schift-ko-pii-v7 모델은 API 키/비밀번호처럼 자유 형식인 시크릿이나
문맥 단어 없는 일반 URL을 거의 탐지하지 못한다(학습 데이터 부족으로
추정). 여기서는 두 종류의 보조 탐지를 제공한다.

1. 카테고리 규칙(_CATEGORY_PATTERNS): 사용자가 체크박스로 켜고 끌 수 있는
   사전 정의 규칙 (비밀번호, API 키, URL).
2. 사용자 지정 단어(detect_custom_words): 사용자가 직접 입력한 단어/구문을
   텍스트에서 그대로 찾아 마스킹 대상에 추가한다.

모델 탐지와 겹치는 구간은 항상 모델 결과를 우선하고, 겹치지 않는
구간만 추가한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CustomSpan:
    start: int
    end: int
    label: str


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    description: str


CATEGORIES: tuple[Category, ...] = (
    Category("password", "비밀번호", "'비밀번호는 ...', 'password: ...' 형태의 값"),
    Category("api_key", "API 키 / 토큰", "sk-, ghp_, AIza 등 알려진 접두사 + 문맥 단어 뒤 토큰"),
    Category("url", "일반 URL / 도메인", "문맥 단어 없는 순수 도메인 (예: example.com/path)"),
)

# (카테고리 id, 라벨, 정규식, 마스킹할 group 번호 — None이면 전체 매치)
_CATEGORY_PATTERNS: tuple[tuple[str, str, re.Pattern, int | None], ...] = (
    (
        "password",
        "secret",
        re.compile(
            r"(?:비밀번호|패스워드|암호|password|pw)\s*(?:는|은|:|：)?\s*"
            r"([A-Za-z0-9!@#$%^&*_\-+=]{6,64})",
            re.IGNORECASE,
        ),
        1,
    ),
    (
        "api_key",
        "secret",
        re.compile(
            r"(?:API\s*키|api\s*key|secret\s*key|access\s*key|access\s*token|"
            r"시크릿\s*키|엑세스\s*키|토큰)\s*(?:는|은|:|：)?\s*"
            r"([A-Za-z0-9_\-\.]{12,128})",
            re.IGNORECASE,
        ),
        1,
    ),
    (
        "api_key",
        "secret",
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_\-]{10,}|pk_[A-Za-z0-9_\-]{10,}|"
            r"ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
            r"AIza[A-Za-z0-9_\-]{20,}|Bearer\s+[A-Za-z0-9_\-\.]{10,})\b"
        ),
        None,
    ),
    (
        "url",
        "private_url",
        re.compile(
            r"\b(?:https?://)?(?:[A-Za-z0-9-]+\.)+"
            r"(?:com|net|org|io|dev|app|co\.kr|kr|me|ai)\b"
            r"(?:/[^\s,)]*)?",
            re.IGNORECASE,
        ),
        None,
    ),
)


def detect_custom(text: str, enabled_categories: set[str]) -> list[CustomSpan]:
    """선택된 카테고리 규칙만으로 보조 탐지. 겹치면 먼저 매치된 것을 우선한다."""
    spans: list[CustomSpan] = []
    for category_id, label, pattern, group in _CATEGORY_PATTERNS:
        if category_id not in enabled_categories:
            continue
        for m in pattern.finditer(text):
            start, end = m.span(group if group is not None else 0)
            if start == -1:
                continue
            spans.append(CustomSpan(start, end, label))
    return _drop_overlaps(spans)


def detect_custom_words(text: str, words: list[str]) -> list[CustomSpan]:
    """사용자가 지정한 단어/구문을 텍스트에서 대소문자 무시하고 그대로 찾는다."""
    spans: list[CustomSpan] = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        for m in re.finditer(re.escape(word), text, re.IGNORECASE):
            spans.append(CustomSpan(m.start(), m.end(), "custom_word"))
    return _drop_overlaps(spans)


def _drop_overlaps(spans: list[CustomSpan]) -> list[CustomSpan]:
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    result: list[CustomSpan] = []
    cursor = -1
    for span in ordered:
        if span.start >= cursor:
            result.append(span)
            cursor = span.end
    return result


@dataclass(frozen=True)
class MergedSpan:
    start: int
    end: int
    label: str
    source: str  # "model" | "rule" | "word"


def merge_with_model_spans(
    text: str,
    model_spans: list[tuple[int, int, str]],
    category_spans: list[CustomSpan],
    word_spans: list[CustomSpan],
) -> list[MergedSpan]:
    """모델 탐지 구간과 보조 탐지 구간들을 합친다.

    겹치면 이미 확정된(먼저 들어온) 구간을 우선한다: 모델 > 카테고리 규칙 > 사용자 단어.
    각 결과 span은 실제로 어느 소스에서 "추가"됐는지 source에 정확히 기록한다.
    """
    merged: list[MergedSpan] = [
        MergedSpan(s, e, label, "model") for s, e, label in model_spans
    ]
    occupied = [(s, e) for s, e, _ in model_spans]

    def overlaps(start: int, end: int) -> bool:
        return any(start < e and s < end for s, e in occupied)

    for group, source in ((category_spans, "rule"), (word_spans, "word")):
        for span in group:
            if not overlaps(span.start, span.end):
                merged.append(MergedSpan(span.start, span.end, span.label, source))
                occupied.append((span.start, span.end))

    return sorted(merged, key=lambda m: m.start)
