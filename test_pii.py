from schift_ko_pii import AnalysisConfig, ProcessingMode, analyze_text

text = "피고 김민수의 전화번호는 010-1234-5678이고, 이메일은 minsu@example.com입니다."

# STRICT 모드: 탐지된 PII를 기본적으로 마스킹
result = analyze_text(text, config=AnalysisConfig(mode=ProcessingMode.STRICT))

print("원문:      ", text)
print("마스킹 결과:", result.masking.masked_text)
print()
print("탐지된 항목:")
for d in result.detections:
    print(f"  - [{d.label}] '{text[d.span.start:d.span.end]}' (score={d.score:.4f})")

print()
print("요약:", result.summary)
