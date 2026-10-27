# woka-writing-style : 한국어 문서 문체 플러그인

Claude Code로 만드는 한국어 문서(보고서, 제안서, 이메일, 노션 페이지, 강의자료 등)의 문체를 일정한 격식 기준으로 유지해 주는 플러그인입니다. 설치하면 세션이 시작될 때마다 문체 규칙이 자동으로 적용되고, 문서 작업 시 AI 문체 제거와 맞춤법 검수 스킬이 함께 동작합니다.

## 구성

| 구성요소 | 역할 |
|---|---|
| 문체 규칙 (`hooks/style-rules.md`) | 감성과잉 차단, 구어 비유 동사 교체표, 줄글 존댓말과 개괄식 개조식 구분, 표식 라벨 금지, 번역체 교정, 줄표와 가운뎃점 금지, 문장 완결성, 출력 전 셀프체크(차단 1~8) |
| `humanizer` 스킬 | AI 특유의 문체(의미 부풀리기, 번역투, 과잉 나열 등 30개 패턴) 제거. 격식 문서는 격식 모드로 보수적 윤문 |
| `korean-spell-check` 스킬 | 바른한글(나라 맞춤법 검사기) 기반 오탈자, 띄어쓰기 검수 |

## 설치

Claude Code에서 아래 두 명령을 순서대로 입력합니다.

```
/plugin marketplace add jinbaek-woka/woka-writing-style
/plugin install woka-writing-style@woka-writing-style
```

설치 후 새 세션을 시작하면 문체 규칙이 적용됩니다. `/plugin` 메뉴에서 설치 상태 확인이 가능합니다.

## 동작 방식

- 문체 규칙은 세션 시작 시점에 한 번 브리핑되는 방식으로 적용됩니다. 사용자의 CLAUDE.md, 설정 파일은 수정하지 않습니다.
- 규칙은 문서 산출물의 한국어 본문에만 적용됩니다. 일상 대화, 코드, 진행 상황 보고에는 적용되지 않습니다. 각자의 CLAUDE.md에서 채팅 답변까지 범위를 넓힐 수 있습니다.

## 업데이트, 해제

- 자동 업데이트 켜기(권장) : `/plugin` 입력 → Marketplaces 탭 → `woka-writing-style` 선택 → Enable auto-update. 켜 두면 이후 갱신을 Claude Code 사용 중에 자동으로 내려받고, 다음 세션부터 적용됩니다.
- 수동 업데이트 : `/plugin` 입력 → Installed 탭 → `woka-writing-style` 선택 → Update now. 적용은 `/reload-plugins` 또는 다음 세션.
- 일시 해제 : `/plugin` 메뉴에서 비활성화(disable)
- 삭제 : `/plugin` 메뉴에서 제거(uninstall). 삭제 시 흔적 없이 원래 상태로 복구

## 유의사항

- 맞춤법 검수는 외부 맞춤법 검사기(nara-speller.co.kr)에 텍스트를 전송하는 방식입니다. 기밀성 높은 문서는 맞춤법 검수를 생략하도록 규칙에 반영되어 있습니다.
- 검사기 정책상 저빈도, 비상업 용도로만 사용합니다.

## 크레딧

- `humanizer` 스킬 : [blader/humanizer](https://github.com/blader/humanizer) (MIT)를 한국어 환경에 맞게 재구성한 판. 격식 모드는 [epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai)의 윤문 원칙 일부 반영
- 맞춤법 검사 : [바른한글(구 부산대 맞춤법 검사기)](https://nara-speller.co.kr/speller/)
- 문장 완결성 규칙(차단 8) : [snflkd/fluent-korean](https://github.com/snflkd/fluent-korean) (MIT)의 일부 항목을 요약해 반영

© Woka. All Rights Reserved
