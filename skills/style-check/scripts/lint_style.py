#!/usr/bin/env python3
"""문체 낱말 검사 : 텍스트 파일에서 문체 규칙 위반 후보 낱말을 찾아 "파일:줄번호 [번호묶음] 낱말 | 앞뒤 30자"로 보여 줍니다.
사용 : python3 lint_style.py <텍스트 파일 …> [--out 폴더] [--rules-root 플러그인_뿌리] [--formal 격식모드.md] [--project 프로젝트_폴더]
점검표 위치와 원천은 build_checklist.py와 같은 인자로 찾고, 점검표가 없거나 원천보다 오래되면 다시 만듭니다. 찾은 것은 후보이며 판정은 사람이 합니다.
"""
import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # 이 폴더에 __pycache__를 만들지 않음
sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I로 실행해도 같은 폴더의 build_checklist를 찾음
import build_checklist as bc  # noqa: E402


def V(stem):
    """동사 줄기와 활용형(끝 글자에 ㄴ, ㄹ, ㅂ 받침이 붙은 꼴. 굴린, 굴릴, 굴립니다)을 함께 찾는 식."""
    code = ord(stem[-1]) - 0xAC00
    base = code - code % 28
    return stem[:-1] + "[" + "".join(chr(0xAC00 + base + f) for f in (0, 4, 8, 17)) + "]"


def FINAL(index):
    """받침이 index(ㄴ=4, ㄹ=8)인 글자 모음. 정규식에 낱자 ㄹ을 그대로 쓰면 '할'에 맞지 않아서 만듭니다."""
    return "[" + "".join(chr(0xAC00 + i * 28 + index) for i in range(19 * 21)) + "]"


NB = r"(?<![가-힣])"  # 앞 글자가 한글이 아닐 때만(목적은, 모자란, 덮어쓰기 같은 낱말 속 글자 제외)

TIME = [r"오늘", r"어제", r"내일", r"방금", NB + r"아까(?![운워울웠])"]  # 편성 종속 시간 표현(코드 줄에서도 검사)

# 묶음 이름은 점검표 번호 머리와 같습니다. 한 줄에 정규식 하나씩 더하면 됩니다.
# (정규식, "따옴표 밖") : 따옴표 안이면 건너뜀. (정규식, "제목 제외") : #으로 시작하는 줄은 건너뜀.
PATTERNS = {
    "B2": [  # 차단 2 구어 비유 동사 표
        V("굴리"), NB + V("돌리"), r"못박", V("손을 대"), V("손대"), r"한 발씩", V("들고 가"),
        V("잡아두"), r"거들|거드는|거듭니다", NB + r"박(?:다|아|혀|힌|힙|는다|습니다)",
        V("꺼내 쓰"), r"꺼내 써", V("굳히"), V("쌓아두"), r"닿아 있", V("닫아 두"), r"문턱",
        V("깎이"), V("흐려지"), V("비대해지"), r"소환",
        NB + r"적(?:다|기|어(?!도)|은|지(?! 않)|고|습니다|으세요)",  # 적다(작성 뜻). 적어도, 적지 않은 제외
        NB + r"(?:쓰(?:다|기|는|고|면|지)|씁니다|쓸 |써(?:서|야|도| ))",  # 쓰다(글이면 작성, 도구면 사용)
        NB + V("자라"), r"몫", r"빈자리", r"흔적", r"입에 붙",
    ],
    "FP": [  # 격식 모드 원칙 2 낱말 격식
        r"알아서", r"통째", r"그때그때", r"한 번 한 번", r"한참", r"제각각", r"결국", r"한마디로",
        NB + r"짠 ", NB + r"짜서", NB + r"치지 않", NB + r"치면",
        NB + r"열고", NB + r"엽니다", NB + r"열어 ", NB + r"풀[리린릴립다어]", NB + r"풉니다",
        r"나온 답", r"(?<![가-힣\d])쪽(?:은|의|이|에서)",
        r"해 ?줍니다", r"줍니다", (r"해줘", "따옴표 밖"),
        r"지금 ?:", NB + r"되게", r"엄청", r"그냥", NB + r"딱 ",
    ],
    "B3": [  # 차단 3 종결
        FINAL(8) + r"까(?!지)",  # ~ㄹ까(할까, 일까, 볼까). 3일까지 제외
        r"나\?",
        r"(?<![세필중개수소주강])요(?=[.!?]|$)",  # 해요체. 하세요., 필요., 중요. 제외
        r"죠", r"거든",
        r"(?<=[가-힣])(?<!니)다(?=[.!]|$)",  # 한다체(~한다., ~이다., ~있다.). ~습니다.와 목록 머리 "다."는 제외
        r"십시오", FINAL(17) + r"니까",  # ~습니까, ~입니까, ~합니까(하니까 같은 이음말 제외)
    ],
    "B4": [  # 차단 4 표식 라벨
        r"한 줄 요약", r"정리하면", r"결론부터", r"TL;DR", r"(?:핵심|요약)\**\s?:",
    ],
    "B5": [  # 차단 5 번역체
        r"[을를] 통해", r"에 있어", r"에 대[한해]", r"로부터", r"에 의해", r"존재하", r"이루어지",
        r"것이 (?:가능|필요|중요)", r"측면", r"차원에서", r"영역", r"접근(?!\s?(?:권한|통제|제어|차단|허용|범위))", r"관점", r"요소",
        r"하나의 ", r"한 가지를", r"하나를 ", r"한 줄로", r"에서의", r"으로의", r"에의 ",
    ],
    "B6": [  # 차단 6 줄표와 쌍점(주소와 `코드`는 미리 지움, 10:20 같은 시각과 3:1 같은 비율은 걸리지 않음)
        r"[—―]",
        r"(?<=\S) - (?=\S)",  # 줄표 대용 붙임표(줄 앞 불릿 기호는 제외)
        r"[가-힣A-Za-z)*]:",  # 앞에 붙인 쌍점(예:, 질문:)
        r"[가-힣] :(?=\S)",  # 뒤에 붙인 쌍점(제목 :설명)
        # 조사 뒤 쉼표. 이, 가, 로, 에, 도, 만, 과는 평가, 그대로, 때문에, 조직도, 이지만, 결과 같은 낱말 끝과 겹쳐 뺌.
        r"(?:은|는|을|를|(?<!적)으로|에서|에게|와),",
    ],
    "B7": [  # 차단 7 가운뎃점과 나열
        r"[·ㆍ]",
        NB + r"및(?![가-힣])(?=.*" + NB + r"및(?![가-힣]))",  # 한 줄에 '및'이 두 번 이상
    ],
    "B9": [  # 차단 9 마침표 후보(제목, 이름 칸일 수 있음)
        (r"(?:다|함|음|됨|임|짐|기|요)\s*$", "제목 제외"),
    ],
    "LN": [  # 노션 강의자료 스킬 4-2 시간 표현, 3-9 도구명
        *TIME,
        r"Claude Code", r"클로드코드", r"스킬(?!명)", r"구글 AI 스튜디오", r"깃허브", r"버셀",
    ],
    "FS": [  # 격식 모드 사용자 지적 표본 낱말
        r"묶음", r"맞는 일", r"실체", r"읽[히힙혀힌힐]", r"봅니다", r"풀립니다", V("자리로 가"),
        r"돌아갑니다", NB + r"자란", V("건네"),
    ],
}

# 코드 줄과 코드 블록 안에서도 검사하는 묶음(복붙용 프롬프트는 자기완결이고 줄표와 가운뎃점을 쓰지 않음). 나머지 묶음은 코드를 건너뜀.
CODE_PATTERNS = {"LN": TIME, "B6": [r"[—―]"], "B7": [r"[·ㆍ]"]}

FENCE = re.compile(r"^\s*(```|~~~)")
MASK = re.compile(r"http\S*|`[^`]*`")  # 주소와 `코드`는 같은 길이의 빈 글자로 지움
DUMP = re.compile(r"^\s*\[[0-9A-Fa-f-]{8,}\]\s+([a-z_0-9]+):\s?")  # 노션 블록 목록 줄 머리 "[블록 ID] 종류: "


def compiled(patterns=None):
    out = {}
    for group, pats in (patterns or PATTERNS).items():
        out[group] = [(re.compile(p[0]), p[1]) if isinstance(p, tuple) else (re.compile(p), None) for p in pats]
    return out


QUOTE_PAIRS = {'"': '"', "“": "”", "‘": "’"}


def quote_spans(line):
    """따옴표로 감싼 구간 [(시작, 끝), …]. 여는 따옴표는 짝이 맞는 닫는 따옴표에서만 닫힙니다."""
    spans, closer, start = [], None, 0
    for i, ch in enumerate(line):
        if closer is None and ch in QUOTE_PAIRS:
            closer, start = QUOTE_PAIRS[ch], i
        elif closer is not None and ch == closer:
            spans.append((start, i))
            closer = None
    return spans


def lint(path, rules, code_rules, counts):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    fence = False
    for no, raw in enumerate(text.splitlines(), 1):
        line = unicodedata.normalize("NFC", raw)
        if FENCE.match(line):
            fence = not fence
            continue
        dump = DUMP.match(line)
        kind = dump.group(1) if dump else ""
        in_code = fence or kind == "code" or line.lstrip().startswith("code:")
        line = line[dump.end():] if dump else line  # 블록 ID와 종류 이름은 검사하지 않음
        masked = MASK.sub(lambda m: "\0" * len(m.group()), line)
        heading = line.lstrip().startswith("#") or kind.startswith("heading") or kind == "toggle" or kind == "callout"  # 콜아웃 줄은 제목 줄
        quotes = quote_spans(line)
        for group, pats in (code_rules if in_code else rules).items():
            hits = []
            for rx, opt in pats:
                if opt == "제목 제외" and heading:
                    continue
                for m in rx.finditer(masked):
                    if opt == "따옴표 밖" and any(a < m.start() < b for a, b in quotes):
                        continue
                    hits.append((m.start(), m.end()))
            end = -1
            for s, e in sorted(hits, key=lambda h: (h[0], -h[1])):
                if s < end:
                    continue  # 같은 묶음에서 겹치는 자리는 한 번만
                end = e
                counts[group] += 1
                print(f"{path}:{no} [{group}] {line[s:e].strip()} | {line[max(0, s - 30):e + 30].strip()}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", help="검사할 텍스트 파일")
    bc.add_source_args(ap)
    args = ap.parse_args(argv)
    try:
        items, path = bc.ensure(args)
        note = f"규칙 전체 판정은 점검표({len(items)}개 항목)와 check_coverage.py로 합니다. 위치 : {path.with_name(bc.MD_NAME)}"
    except SystemExit:
        note = "점검표를 확인하지 못해 낱말 검사만 했습니다(위 오류 참고)."
    rules, code_rules, counts, missing = compiled(), compiled(CODE_PATTERNS), Counter(), []
    for f in args.files:
        try:
            lint(f, rules, code_rules, counts)
        except FileNotFoundError:
            missing.append(f)
    print("묶음별 건수")
    for group in PATTERNS:
        print(f"  {group:<3} {counts[group]:>3}건")
    print(f"합계 {sum(counts.values())}건")
    print("찾은 항목은 위반 후보입니다. 위반인지는 사람이 문장을 읽고 판정합니다.")
    print(note)
    for f in missing:
        print(f"파일이 없습니다. 위치 : {f}", file=sys.stderr)
    return 2 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
