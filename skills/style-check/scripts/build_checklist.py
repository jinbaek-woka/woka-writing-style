#!/usr/bin/env python3
"""문체 점검표 생성 : 규칙 파일을 실행할 때마다 다시 읽어 규칙 줄마다 번호를 붙이고 점검표.md와 점검표.json을 만듭니다.
사용 : python3 build_checklist.py [--figure] [--out 폴더] [--rules-root 플러그인_뿌리] [--formal 격식모드.md] [--project 프로젝트_폴더]
기본값 : --out 현재 폴더, --rules-root 스크립트 위쪽의 플러그인 뿌리(찾지 못하면 오류), --formal 뿌리 안 격식 모드, --project 현재 폴더 위쪽의 CLAUDE.md 폴더(없으면 선택 원천은 건너뜀), --figure는 그림 규격(LG) 포함.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

STYLE_REL = Path("hooks/style-rules.md")
FORMAL_REL = Path("skills/humanizer/references/formal-mode.md")
NOTION_REL = Path(".claude/skills/lecture-notion/SKILL.md")
MD_NAME, JSON_NAME = "점검표.md", "점검표.json"

# 원천 : (점검표에 적는 이름, 필수 여부). 필수 원천은 파일이나 절이 없으면 오류, 선택 원천은 건너뜀.
SOURCES = {
    "style": ("style-rules.md", True),
    "formal": ("formal-mode.md", True),
    "claude": ("CLAUDE.md", False),
    "notion": ("lecture-notion/SKILL.md", False),
}

# 뽑는 규칙 : (번호 머리, 원천, 제목 줄 앞부분, 뽑는 방식, 포함 낱말, 비고, 절이 끝나는 제목 단계)
# 뽑는 방식 : bullets 불릿 / list 불릿과 번호 항목 / sent 불릿, 번호 항목, 문단 문장 / rows 표 행 / para 문단 / quote 인용 / first 첫 불릿
# 절은 같은 단계 이상의 다음 제목 전까지(끝 단계를 주면 그 단계 이상의 제목 전까지)
CHAT_WORDS = ["차단 1~9", "숫자 표기", "개발 용어", "절대경로", "비유 표현"]
RULES = [("SCOPE-", "style", "## 적용 범위", "bullets", None, "", None)]
for _n in range(1, 10):
    RULES.append((f"B{_n}-", "style", f"## 차단 {_n} ", "sent", None, "", None))
    if _n == 2:
        RULES.append(("B2-T", "style", "## 차단 2 ", "rows", None, "", None))
RULES += [
    ("CM-", "style", "## 점검 방법", "sent", None, "", None),  # 절이 없으면 건너뜀(OPTIONAL)
    ("SCR-", "style", "## 화면 문구 예외", "sent", None, "화면 문구", None),
    ("SC-", "style", "## 출력 직전 셀프체크", "sent", None, "", None),
    ("AU-", "style", "## 자동 검수 절차", "list", None, "", None),
    ("FP-", "formal", "## 6대 원칙", "list", None, "", None),
    ("FE-", "formal", "## 줄글 = 존댓말 / 개괄식 = 개조식", "rows", None, "", None),
    ("FT1-", "formal", "### ①", "rows", None, "", None),
    ("FT2-", "formal", "### ②", "rows", None, "", None),
    ("FT3-", "formal", "### ③", "rows", None, "", None),
    ("FT4-", "formal", "### ④", "rows", None, "", None),
    ("FS-", "formal", "### 사용자 지적 표본", "rows", None, "", None),
    ("FV-", "formal", "## 격식 모드 자체검증", "list", None, "", None),
    ("FD-", "formal", "## 규칙별 결정 이력", "rows", None, "", None),
    ("CK-", "claude", "# 한국어 본문 격식", "bullets", None, "", 2),
    ("CH-", "claude", "## humanizer 자동 적용", "para", None, "", None),
    ("CS-", "claude", "## 문체 점검은 낱말 검색으로 끝내지 않는다", "list", None, "", None),
    ("CR-", "claude", "## 보고, 질문 규칙", "bullets", CHAT_WORDS, "채팅", None),
    ("LN-", "notion", "## 노션 강의자료 제작 스킬", "quote", ["본문 문체 규칙(필수)"], "", None),
    ("LN-", "notion", "## ⛔ BLOCKING GATE", "list", ["시점 표현"], "", None),
    ("LN-", "notion", "### 3-6.", "bullets", ["줄표"], "", None),
    ("LN-", "notion", "### 3-9.", "bullets", None, "", None),
    ("LN-", "notion", "### 4-1.", "first", None, "", None),
    ("LN-", "notion", "### 4-2.", "bullets", ["편성 종속"], "", None),
    ("LN-", "notion", "### 6-1.", "bullets", ["확장자"], "", None),
    ("LG-", "notion", "### 3-8.", "bullets", None, "그림", None),  # --figure일 때만
]

OPTIONAL = {"CM-", "SX-"}  # 원천에 절이 아직 없어도 오류로 보지 않는 번호 머리
HEAD = re.compile(r"^(#{1,6})\s")
BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
NUMBER = re.compile(r"^\s*\d+[.)]\s+(.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")
RULE_LINE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
SEP = re.compile(r"^\s*\|?\s*:?-{3,}")
PIPE = re.compile(r"(?<!\\)\|")


def nfc(path):
    """맥에서 경로가 풀어쓴 한글(NFD)로 올 때가 있어 모아쓴 한글(NFC)로 맞춥니다."""
    return Path(unicodedata.normalize("NFC", str(path)))


def clean(text):
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def cells(line):
    """표 한 줄을 칸 목록으로 나눕니다. \\| 는 칸 구분으로 보지 않습니다."""
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip() for c in PIPE.split(s)]


def section(lines, head, stop=None):
    """head로 시작하는 제목 줄을 찾아 (제목, 본문 줄)을 돌려줍니다. 없으면 (None, [])."""
    fence, title, start, level = False, None, 0, 0
    for i, line in enumerate(lines):
        if FENCE.match(line):
            fence = not fence
        m = None if fence else HEAD.match(line)
        if not m:
            continue
        if title is None:
            if line.startswith(head):
                title, start, level = line.lstrip("#").strip(), i + 1, stop or len(m.group(1))
        elif len(m.group(1)) <= level:
            return title, lines[start:i]
    return title, (lines[start:] if title else [])


def blocks(lines):
    """줄을 [종류, 글] 블록으로 나눕니다. 종류 : bullet, number, row, quote, para. 코드 블록과 가로줄은 건너뜁니다."""
    out, cur, table, fence = [], None, [], False

    def end_table():
        rows = table[2:] if len(table) > 1 and SEP.match(table[1]) else table  # 머리 행과 구분 행 제외
        out.extend(["row", " | ".join(cells(r))] for r in rows if not SEP.match(r))
        table.clear()

    for line in lines:
        if FENCE.match(line):
            fence, cur = not fence, None
            continue
        if fence:
            continue
        if line.lstrip().startswith("|"):
            table.append(line)
            cur = None
            continue
        if table:
            end_table()
        if not line.strip() or RULE_LINE.match(line):
            cur = None
            continue
        m = BULLET.match(line) or NUMBER.match(line)
        if m:
            cur = ["bullet" if BULLET.match(line) else "number", m.group(1)]
            out.append(cur)
        elif line.lstrip().startswith(">"):
            text = line.lstrip()[1:].strip()
            if cur and cur[0] == "quote":
                cur[1] += " " + text
            else:
                cur = ["quote", text]
                out.append(cur)
        elif cur:
            cur[1] += " " + line.strip()  # 빈 줄 없이 이어진 줄은 앞 블록에 붙임
        else:
            cur = ["para", line.strip()]
            out.append(cur)
    if table:
        end_table()
    return out


def sentences(text):
    """문단을 문장으로 나눕니다. 괄호 안과 큰따옴표 안의 마침표에서는 나누지 않습니다."""
    out, start, depth, quote = [], 0, 0, False
    for i, ch in enumerate(text):
        if ch in '"“”':
            quote = ch == "“" or (ch == '"' and not quote)
        elif quote:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in ".?!" and depth == 0 and (i + 1 == len(text) or text[i + 1] == " "):
            out.append(text[start:i + 1].strip())
            start = i + 1
    if text[start:].strip():
        out.append(text[start:].strip())
    return out


def pick(blks, mode, words):
    if mode == "sent":
        items = []
        for kind, text in blks:
            if kind in ("bullet", "number"):
                items.append(text)
            elif kind == "para":
                items += sentences(clean(text))
    elif mode == "all":  # 알 수 없는 절 : 불릿, 번호 항목, 문단 문장, 표 행 모두
        items = []
        for kind, text in blks:
            items += sentences(clean(text)) if kind == "para" else [text]
    else:
        kinds = {"rows": ("row",), "para": ("para",), "quote": ("quote",), "bullets": ("bullet",),
                 "first": ("bullet",), "list": ("bullet", "number")}[mode]
        items = [text for kind, text in blks if kind in kinds]
    items = [clean(t) for t in items]
    if words:
        items = [t for t in items if any(w in t for w in words)]
    return items[:1] if mode == "first" else items


def unknown_sections(lines):
    """style-rules.md의 '##' 절 가운데 RULES에 없는 제목을 순서대로 돌려줍니다(어떤 절도 빠지지 않게 하는 용도)."""
    known = [h for _, k, h, *_ in RULES if k == "style"]
    out, fence = [], False
    for line in lines:
        if FENCE.match(line):
            fence = not fence
        if not fence and line.startswith("## ") and not any(line.startswith(h) for h in known):
            out.append(line)
    return out


def find_up(start, test):
    return next((d for d in [start, *start.parents] if test(d)), None)


def add_source_args(ap):
    """세 도구가 함께 쓰는 원천과 점검표 위치 인자."""
    ap.add_argument("--out", default=".", help="점검표.md와 점검표.json을 두는 폴더(기본값 현재 폴더)")
    ap.add_argument("--rules-root", help="플러그인 뿌리(hooks/style-rules.md가 있는 폴더)")
    ap.add_argument("--formal", help="격식 모드 formal-mode.md 경로")
    ap.add_argument("--project", help="CLAUDE.md가 있는 프로젝트 폴더")


def resolve(args):
    """원천 파일 경로와 점검표 폴더를 정합니다."""
    if args.rules_root:
        root = nfc(Path(args.rules_root).expanduser().resolve())
    else:
        here = nfc(Path(__file__).resolve().parent)
        root = find_up(here, lambda d: (d / STYLE_REL).is_file() and (d / FORMAL_REL).is_file())
    if not root or not (root / STYLE_REL).is_file():
        sys.exit(f"플러그인 뿌리(hooks/style-rules.md가 있는 폴더)를 찾지 못했습니다. --rules-root로 지정하세요. 확인한 위치 : {root}")
    style, formal = root / STYLE_REL, root / FORMAL_REL
    if args.formal:
        formal = nfc(Path(args.formal).expanduser().resolve())
    if args.project:
        project = nfc(Path(args.project).expanduser().resolve())
    else:
        project = find_up(nfc(Path.cwd().resolve()), lambda d: (d / "CLAUDE.md").is_file())
    return {"root": root, "out": nfc(Path(args.out).expanduser().resolve()), "style": style, "formal": formal,
            "claude": project / "CLAUDE.md" if project else None,
            "notion": project / NOTION_REL if project else None}


def build(src, figure, quiet=False):
    """점검표를 만들어 저장합니다. 필수 원천에 문제가 있으면 내용을 보여 주고 종료 코드 1로 끝냅니다."""
    out, root = src["out"], src["root"]
    errors, missing_files, missing_parts = [], [], defaultdict(list)
    if out == root or root in out.parents:
        errors.append(f"플러그인 폴더 안에는 점검표를 만들지 않습니다. --out으로 다른 폴더를 지정하세요. 위치 : {out}")
    texts = {}
    for key, (label, required) in SOURCES.items():
        path = src[key]
        if path and path.is_file():
            texts[key] = unicodedata.normalize("NFC", path.read_text(encoding="utf-8")).splitlines()
        elif required:
            errors.append(f"필수 원천 파일이 없습니다({label}). 위치 : {path}")
        else:
            missing_files.append(key)
    items, seq, per_src = [], Counter(), Counter()
    extra = [("SX-", "style", h, "all", None, "", None) for h in unknown_sections(texts.get("style", []))]
    for prefix, key, head, mode, words, note, stop in RULES + extra:
        if (prefix == "LG-" and not figure) or key not in texts:
            continue
        title, body = section(texts[key], head, stop)
        found = pick(blocks(body), mode, words) if title else []
        if not found and prefix in OPTIONAL:
            continue
        if not found:
            if SOURCES[key][1]:
                errors.append(f"{SOURCES[key][0]}의 '{head}' 절에서 뽑은 항목이 0개입니다({prefix.rstrip('-')} 묶음).")
            else:
                missing_parts[key].append(head)
            continue
        for text in found:
            seq[prefix] += 1
            per_src[key] += 1
            items.append({"id": f"{prefix}{seq[prefix]:02d}", "source": f"{src[key]} > {title}",
                          "group": prefix.rstrip("-"), "text": text, "note": note})
    dup = [i for i, n in Counter(x["id"] for x in items).items() if n > 1]
    if dup:
        errors.append("같은 번호가 두 번 나왔습니다 : " + ", ".join(dup))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print("점검표를 만들지 않았습니다. 위 오류를 확인하세요(절이 없다는 오류는 원천 파일의 제목이나 구조가 바뀐 경우입니다).",
              file=sys.stderr)
        sys.exit(1)

    figure_text = "포함" if figure else "미포함(--figure를 붙여 실행하면 포함)"
    head_lines = []
    for key, (label, _) in SOURCES.items():
        if key in missing_files or not per_src[key]:
            head_lines.append(f"  - {label} : 없음(건너뜀)")
        else:
            head_lines.append(f"  - {label} : {per_src[key]}개, 위치 : {src[key]}")
        head_lines += [f"    - '{h}' 절 : 없음(건너뜀)" for h in missing_parts[key]]
    md = ["# 문체 점검표", "",
          f"- 생성 시각 : {datetime.now():%Y-%m-%d %H:%M:%S}",
          f"- 그림 규격(LG 번호) : {figure_text}",
          "- 원천 파일별 항목 수", *head_lines,
          f"- 합계 : {len(items)}개",
          "- 판정 표 작성 방법 : 검토 결과 표의 첫 칸에 번호를 넣고, 판정 칸에는 지킴, 놓침, 해당 없음 가운데 하나로 시작하는 판정을 넣습니다. "
          "작성한 뒤 check_coverage.py로 빠진 번호를 확인합니다.",
          "", "| 번호 | 출처 | 규칙 | 비고 |", "|---|---|---|---|"]
    for x in items:
        path, title = x["source"].split(" > ", 1)
        label = next(lbl for k, (lbl, _) in SOURCES.items() if str(src[k]) == path)
        md.append(f"| {x['id']} | {label} > {title} | {x['text'].replace('|', chr(92) + '|')} | {x['note']} |")
    out.mkdir(parents=True, exist_ok=True)
    (out / JSON_NAME).write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / MD_NAME).write_text("\n".join(md) + "\n", encoding="utf-8")

    if quiet:
        print(f"점검표를 다시 만들었습니다({len(items)}개). 위치 : {out / MD_NAME}")
        return items
    print("묶음별 항목 수")
    for group, n in Counter(x["group"] for x in items).items():
        print(f"  {group:<6} {n:>3}개")
    print("원천 파일별 항목 수")
    print("\n".join(head_lines))
    print(f"합계 {len(items)}개, 그림 규격 {figure_text}")
    print(f"점검표를 만들었습니다. 위치 : {out / MD_NAME}")
    return items


def ensure(args, figure=None):
    """점검표.json을 읽어 (항목, 경로)를 돌려줍니다. 없거나, 원천 파일이나 이 스크립트보다 오래되었거나,
    원천 경로나 그림 규격 포함 여부가 다르면 먼저 다시 만듭니다. figure=None이면 기존 점검표를 따릅니다."""
    src = resolve(args)
    path = src["out"] / JSON_NAME
    reason = "점검표가 없어"
    if path.is_file():
        items = json.loads(path.read_text(encoding="utf-8"))
        has_lg = any(x["group"] == "LG" for x in items)
        figure = has_lg if figure is None else figure
        files = [src[k] for k in SOURCES if src[k] and src[k].is_file()]
        newest = max(p.stat().st_mtime for p in files + [Path(__file__)])
        used = {x["source"].split(" > ", 1)[0] for x in items}
        if path.stat().st_mtime < newest:
            reason = "점검표가 원천 파일보다 오래되어"
        elif not used <= {str(p) for p in files}:
            reason = "원천 파일 경로가 바뀌어"
        elif has_lg != figure:
            reason = "그림 규격 포함 여부가 달라"
        else:
            return items, path
    print(f"{reason} 점검표를 다시 만듭니다.")
    build(src, bool(figure), quiet=True)
    return json.loads(path.read_text(encoding="utf-8")), path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--figure", action="store_true", help="그림 규격(lecture-notion 3-8절) 포함")
    add_source_args(ap)
    args = ap.parse_args(argv)
    build(resolve(args), args.figure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
