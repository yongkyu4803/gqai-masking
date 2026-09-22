import re

from flask import Flask, render_template, request
from markupsafe import Markup, escape

from schift_ko_pii import Action, AnalysisConfig, ProcessingMode, analyze_text

from custom_patterns import (
    CATEGORIES,
    apply_exclusions,
    detect_custom,
    detect_custom_words,
    merge_with_model_spans,
)
from masking_strategies import STYLE_OPTIONS, ReplacementBuilder

app = Flask(__name__)

try:
    with open("sample.txt", encoding="utf-8") as f:
        SAMPLE_TEXT = f.read()
except FileNotFoundError:
    SAMPLE_TEXT = ""

# schift-ko-pii의 기본 STRICT 정책은 private_person/private_url 등을
# "낮은 운영 위험"으로 분류해 BLOCK되지 않는 한 절대 마스킹하지 않는다.
# "전체 마스킹"을 켜면 그 정책과 무관하게 탐지된 모든 항목(모델+추가 규칙+
# 사용자 단어)을 마스킹하고, 끄면 모델이 BLOCK으로 판정한 항목만 마스킹한다.

DEFAULT_ENABLED_CATEGORIES = {c.id for c in CATEGORIES}

SOURCE_LABEL = {"model": "모델", "rule": "추가 규칙", "word": "사용자 단어"}
SOURCE_CSS = {"model": "hl-model", "rule": "hl-rule", "word": "hl-word"}


def _parse_custom_words(raw: str) -> list[str]:
    parts = re.split(r"[,\n]", raw) if raw else []
    seen: list[str] = []
    for part in parts:
        word = part.strip()
        if word and word not in seen:
            seen.append(word)
    return seen


def _render_masked(text: str, items: list, mask_style: str) -> tuple[Markup, str]:
    """마스킹 결과를 강조 표시된 HTML과 순수 텍스트로 함께 만든다."""
    builder = ReplacementBuilder(mask_style)
    masked_parts: list[Markup] = []
    plain_parts: list[str] = []
    cursor = 0

    for item in items:
        masked_parts.append(Markup(escape(text[cursor : item.start])))
        plain_parts.append(text[cursor : item.start])

        original = text[item.start : item.end]
        replacement = builder.replacement_for(item.label, original)
        css = SOURCE_CSS[item.source]
        title = escape(f"{item.label} · {SOURCE_LABEL[item.source]}")

        masked_parts.append(
            Markup(f'<mark class="hl {css}" title="{title}">')
            + escape(replacement)
            + Markup("</mark>")
        )
        plain_parts.append(replacement)
        cursor = item.end

    masked_parts.append(Markup(escape(text[cursor:])))
    plain_parts.append(text[cursor:])

    return Markup("").join(masked_parts), "".join(plain_parts)


@app.route("/", methods=["GET", "POST"])
def index():
    text = ""
    mask_all = True
    custom_words_raw = ""
    exclude_words_raw = ""
    mask_style = STYLE_OPTIONS[0].id
    enabled_categories = DEFAULT_ENABLED_CATEGORIES
    result = None
    error = None

    if request.method == "POST":
        text = request.form.get("text", "")
        mask_all = request.form.get("mask_all") == "on"
        custom_words_raw = request.form.get("custom_words", "")
        exclude_words_raw = request.form.get("exclude_words", "")
        mask_style = request.form.get("mask_style", STYLE_OPTIONS[0].id)
        if mask_style not in {o.id for o in STYLE_OPTIONS}:
            mask_style = STYLE_OPTIONS[0].id
        enabled_categories = {
            c.id for c in CATEGORIES if request.form.get(f"cat_{c.id}") == "on"
        }

        if not text.strip():
            error = "분석할 텍스트를 입력해 주세요."
        else:
            analysis = analyze_text(
                text, config=AnalysisConfig(mode=ProcessingMode.STRICT)
            )

            model_scores = {
                (d.span.start, d.span.end): d.score for d in analysis.detections
            }
            model_spans = [
                (d.span.start, d.span.end, d.label) for d in analysis.detections
            ]
            category_spans = detect_custom(text, enabled_categories)
            custom_words = _parse_custom_words(custom_words_raw)
            word_spans = detect_custom_words(text, custom_words)

            all_spans = merge_with_model_spans(
                text, model_spans, category_spans, word_spans
            )
            exclude_words = _parse_custom_words(exclude_words_raw)
            all_spans = apply_exclusions(text, all_spans, exclude_words)

            if mask_all:
                items = all_spans
            else:
                blocked = {
                    (a.start, a.end)
                    for a in analysis.actions
                    if a.action is Action.BLOCK
                }
                items = [m for m in all_spans if (m.start, m.end) in blocked]

            masked_html, masked_text = _render_masked(text, items, mask_style)

            result = {
                "masked_html": masked_html,
                "masked_text": masked_text,
                "detections": [
                    {
                        "label": m.label,
                        "value": text[m.start : m.end],
                        "score": (
                            round(model_scores[(m.start, m.end)], 4)
                            if m.source == "model"
                            else None
                        ),
                        "source": SOURCE_LABEL[m.source],
                        "source_dot": f"dot-{m.source}",
                        "masked": (m.start, m.end)
                        in {(i.start, i.end) for i in items},
                    }
                    for m in all_spans
                ],
                "summary": {
                    "total": len(items),
                    "from_model": sum(1 for m in items if m.source == "model"),
                    "from_rules": sum(1 for m in items if m.source == "rule"),
                    "from_words": sum(1 for m in items if m.source == "word"),
                },
            }

    return render_template(
        "index.html",
        text=text,
        mask_all=mask_all,
        custom_words_raw=custom_words_raw,
        exclude_words_raw=exclude_words_raw,
        mask_style=mask_style,
        style_options=STYLE_OPTIONS,
        categories=CATEGORIES,
        enabled_categories=enabled_categories,
        result=result,
        error=error,
        sample_text=SAMPLE_TEXT,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
