# 2609_ko_pii

[schift-ko-pii-v7](https://huggingface.co/schift-io/schift-ko-pii-v7) 기반 한국어 개인정보(PII) 탐지/마스킹 로컬 웹앱 (Flask, GQAI 디자인 시스템 적용).

## 원본 모델

| 항목 | 내용 |
|------|------|
| 모델 | [schift-io/schift-ko-pii-v7](https://huggingface.co/schift-io/schift-ko-pii-v7) (Hugging Face) |
| 배포처 | Schift, Inc. (Room821 Co., Ltd.) |
| 태스크 | Token Classification (NER 기반 PII 탐지) |
| 아키텍처 | "hydra encoder" — 공유 하위 레이어 위에 독립적인 상위 레이어(태스크별 헤드)를 얹은 구조 |
| 베이스 | LFM2 계열 bidirectional 인코더 (커스텀 모델링 코드 `modeling_lfm2_bidirectional.py`, 최초 실행 시 HF에서 `trust_remote_code`로 자동 다운로드) |
| 파라미터 수 | 약 4천만(40M) |
| 라이선스 | Schift License v2.0 (Apache 2.0 기반 + 매출 조건, 아래 "라이선스 주의" 참고) |
| Python 패키지 | [`schift-ko-pii`](https://pypi.org/project/schift-ko-pii/) (PyPI) — 이 앱이 직접 호출하는 래퍼. 자체 정책 엔진(`policy.py`), 마스킹 전략, 확장 탐지기(`ko-pii` 어댑터)를 포함 |

이 앱은 모델 자체를 재학습하거나 수정하지 않고, `schift-ko-pii` 패키지의 `analyze_text()`를 그대로 호출한다. `custom_patterns.py`의 보조 정규식 탐지기는 이 모델이 놓치는 패턴(API 키, 비밀번호, 문맥 단어 없는 URL)을 보완하기 위해 이 프로젝트에서 추가한 것이며 원본 모델의 일부가 아니다.

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

```bash
source .venv/bin/activate
python app.py
```

브라우저에서 http://127.0.0.1:5001 접속.

## 탐지 파이프라인

1. **모델 탐지** — schift-ko-pii-v7이 이름/전화/이메일/주소/계좌번호 등을 탐지 (항상 적용).
2. **추가 규칙** (체크박스로 켜고 끔) — 모델이 놓치는 패턴 보완:
   - 비밀번호 (`비밀번호는 ...`, `password: ...`)
   - API 키 / 토큰 (`sk-`, `ghp_`, `AIza` 등 알려진 접두사, 또는 문맥 단어 뒤 토큰)
   - 일반 URL / 도메인 (문맥 단어 없는 순수 도메인, 예: `example.com/path`)
   - 주민등록번호 — `ko-pii`(extended 의존성)의 체크섬·생년월일 검증 정규식 탐지기. 모델은 512토큰 청크 단위로 처리하므로 긴 문서에서 청크 경계에 걸리면 놓칠 수 있는데, 이 탐지기는 원문 전체를 한 번에 훑어 그런 경우를 보완한다
3. **사용자 지정 단어** — 위 규칙에 없는 임의의 단어/구문을 쉼표 또는 줄바꿈으로 입력하면 텍스트에서 그대로 찾아 마스킹 대상에 추가. 모델·규칙과 겹치는 구간은 자동으로 중복 제외.
4. **제외 단어** — 모델/규칙이 반복적으로 잘못 탐지(오탐)하는 값을 쉼표 또는 줄바꿈으로 입력하면 마스킹 대상에서 제외. 출처(모델/규칙/사용자 단어)와 무관하게 텍스트가 완전히 일치하면 걸러진다.

네 가지가 겹치면 **모델 > 추가 규칙 > 사용자 단어** 순으로 우선순위를 가지며(제외 단어는 마지막에 별도로 필터링), 탐지 결과 표의 "출처" 컬럼에서 어디서 잡혔는지 확인할 수 있다.

새로운 패턴이 계속 새는 경우:
- 흔한 형식이면 `custom_patterns.py`의 `_CATEGORY_PATTERNS`에 정규식 규칙을 추가
- 일회성/특정 텍스트면 화면의 "사용자 지정 단어" 입력란 사용
- 반대로 특정 값이 반복적으로 오탐되면 "제외 단어" 입력란 사용

### 알려진 한계와 대응

- **긴 문서에서 모델 탐지가 청크 경계에 걸려 값을 놓칠 수 있음** — 모델은 내부적으로 512토큰 단위 슬라이딩 윈도우(64토큰 겹침)로 청킹한다. 주민등록번호처럼 형식이 정형화된 값은 위의 "주민등록번호" 추가 규칙으로 보완 가능하지만, 정형화되지 않은 값(예: 청크 경계에 걸린 인명)은 규칙으로 고치기 어렵다 — 결과를 검토하고 "사용자 지정 단어"로 직접 추가해야 한다.
- **모델 자체의 오탐(false positive)은 재학습 없이는 근본적으로 못 고침** — 예: 사번 일부("P-1029")를 주소로, "대외비" 같은 일반 단어를 인명으로 잘못 태깅하는 경우가 있다. 완전한 자동 해결책은 없으며, 탐지 결과 표의 신뢰도(score)를 참고해 사람이 검수하고 "제외 단어"로 걸러내는 것이 현실적인 대응이다.

## 탐지 라벨

| 라벨 | 설명 | 출처 |
|------|------|------|
| `private_person` | 인명 | 모델 |
| `private_phone` | 전화번호 | 모델 |
| `private_email` | 이메일 | 모델 |
| `private_address` | 주소 | 모델 |
| `account_number` | 계좌/신원번호 | 모델 |
| `private_url` | URL/IP | 모델 + 추가 규칙 |
| `secret` | API 키, 비밀번호 | 추가 규칙 |
| `custom_word` | 사용자 지정 단어 | 사용자 입력 |

## 마스킹 옵션

- **탐지된 항목 전체 마스킹** 체크 시 — 라이브러리 기본 위험도 정책과 무관하게 탐지된 모든 항목을 마스킹 (이름/URL 등 "저위험" 판정 항목 포함).
- 체크 해제 시 — schift-ko-pii 라이브러리의 STRICT 정책 그대로 사용 (BLOCK 판정된 항목만 마스킹).

### 마스킹 표기 방식 (`masking_strategies.py`)

라디오 버튼으로 선택하며, 선택한 방식이 마스킹 결과 전체(화면·클립보드 복사·파일 저장)에 동일하게 적용된다.

| 방식 | 설명 | 예시 (`김민수`) |
|------|------|------|
| 토큰 표기 | 라벨+순번으로 표기 (기본값) | `[PII_PERSON_1]` |
| 특수기호 (법원식) | 글자를 `○`로 치환, `-`·`.`·`@`·`/`·공백 같은 구분 기호는 유지해 형태만 남김 | `○○○` |
| 가명 치환 | 그럴듯한 가짜 값으로 치환. **같은 원문은 문서 내에서 항상 같은 가명**으로 치환되어(캐시), 실제 값 노출 없이 동일 인물/값 여부는 알아볼 수 있음 | `김도윤` |
| 완전 마스킹 | 원문의 형태·길이 정보 없이 전부 가림 | `[REDACTED]` |

## 화면 구성

- **내브바** — 상단 고정, 브랜드 마크 + "샘플 불러오기" 버튼(sample.txt 내용을 원문 입력창에 채움).
- **2단 레이아웃** — 좌측 "검사할 텍스트"(원문 입력 + 탐지 옵션 접이식 패널 + 분석하기 버튼), 우측 "결과"(마스킹 결과 + 클립보드 복사/텍스트 파일 저장 버튼 + 통계). 1023px 이하에서는 세로로 쌓임.
- **탐지 옵션** — 원문 입력창 바로 아래 `<details>` 접이식 패널에 추가 탐지 규칙 체크박스, 사용자 지정 단어 입력, 제외 단어 입력, 마스킹 표기 방식(4종), 전체 마스킹 토글이 모두 들어있음.
- **결과 액션** — "클립보드 복사"(Clipboard API, 실패 시 구형 execCommand로 폴백)와 "텍스트 파일로 저장"(`masked_result_YYYYMMDD_HHMMSS.txt` 다운로드) 버튼. 성공/실패 여부를 결과 상단에 라이브 리전으로 안내.
- **탐지된 항목 테이블** — 라벨/값/신뢰도/출처/마스킹 여부 (전체 너비 카드, 2단 레이아웃 아래).

## 디자인

`static/gqai-tokens.css` + `static/app.css`로 GQAI 디자인 시스템(에메랄드/근흑 팔레트, 6px 컨트롤·12px 카드 radius, Inter/Noto Sans KR) 적용.

## 라이선스 주의

- 저작권: **Copyright (c) 2026 Schift, Inc. (Room821 Co., Ltd.)**
- 라이선스: **Schift License v2.0** ([전문](https://huggingface.co/schift-io/schift-ko-pii-v7/blob/main/LICENSE), Apache 2.0 기반). 연매출 1천만 달러(USD 10,000,000)를 초과하는 법인은 상업적 이용 시 별도 라이선스가 필요합니다 — 문의: hello@schift.io. 연구/교육/평가/개인 프로젝트/비영리 이용은 매출 규모와 무관하게 항상 허용됩니다.
- 이 앱은 `schift-ko-pii` 패키지를 `pip install`로 의존성으로만 사용하며, 모델 소스코드나 가중치를 이 저장소에 복사·재배포하지 않습니다. 따라서 Apache 2.0 4조(재배포 시 LICENSE 사본 동봉, 변경 파일 고지, NOTICE 파일 전달)는 이 저장소에 적용되지 않습니다.

## 인용

이 앱이 사용하는 모델을 인용할 때는 원저작자(Schift Inc.)가 명시한 아래 BibTeX를 사용하세요.

```bibtex
@software{schift_ko_pii_2026,
  author = {Schift Inc.},
  title = {schift-ko-pii: Korean PII Detection Model},
  year = {2026},
  url = {https://huggingface.co/schift-io/schift-ko-pii-v7},
}
```

## 참고

- 최초 실행 시 Hugging Face에서 모델 가중치와 커스텀 모델링 코드(`modeling_lfm2_bidirectional.py`)를 자동 다운로드합니다 (trust_remote_code).
- `custom_patterns.py`의 정규식 보조 탐지기는 정해진 패턴에만 반응하는 한계가 있습니다.
