#!/usr/bin/env python3
"""문체 점검 누락 검사 : 검토 결과 md의 판정 표에서 점검표 번호가 빠지거나 판정되지 않은 것을 찾습니다.
사용 : python3 check_coverage.py <검토 결과 md> [--figure] [--out 폴더] [--rules-root 플러그인_뿌리] [--formal 격식모드.md] [--project 프로젝트_폴더]
점검표는 --out 폴더(기본값 현재 폴더)의 점검표.json을 읽고, 없거나 원천보다 오래되면 build_checklist.py와 같은 인자로 다시 만듭니다. 빠짐이나 미판정이 있으면 "검수 미완료"(종료 코드 1), 없으면 "누락 없음"(종료 코드 0)입니다.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True  # 이 폴더에 __pycache__를 만들지 않음
sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I로 실행해도 같은 폴더의 build_checklist를 찾음
import build_checklist as bc  # noqa: E402

# 판정 칸 : 지킴, 놓침, 해당 없음으로 시작하는 칸("놓침 20", "지킴(4절 1)" 포함). 문장 중간의 낱말은 판정으로 보지 않음.
VERDICT = re.compile(r"^[*_`\s]*(?:지킴|놓침|해당\s*없음)")
BLANK = {"", "-", "–"}
ID_LIKE = re.compile(r"^[A-Z]+\d*-T?\d{2,}$")


def tables(lines):
    """md의 표를 [[칸, ...], ...] 목록으로 돌려줍니다(코드 블록 안의 표와 구분 행 제외)."""
    out, cur, fence = [], [], False
    for line in lines:
        if bc.FENCE.match(line):
            fence = not fence
        is_row = not fence and line.lstrip().startswith("|")
        if is_row and not bc.SEP.match(line):
            cur.append(bc.cells(line))
        elif not is_row and cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("review", help="검토 결과 md 파일")
    ap.add_argument("--figure", action="store_true", help="그림 규격(LG 묶음) 포함판 점검표로 검사")
    bc.add_source_args(ap)
    args = ap.parse_args(argv)
    items, path = bc.ensure(args, args.figure)
    ids = {x["id"]: x for x in items}
    text = unicodedata.normalize("NFC", Path(args.review).read_text(encoding="utf-8"))

    seen, done, bad, unknown = set(), set(), {}, set()
    for table in tables(text.splitlines()):
        rows = [(re.sub(r"[*_`\s]", "", r[0]), r[1:]) for r in table if r]
        unknown |= {rid for rid, _ in rows if rid not in ids and ID_LIKE.match(rid)}
        rows = [(rid, c) for rid, c in rows if rid in ids]
        # 판정 열 : 이 표에서 판정으로 시작하는 칸이 있는 열과 그 사이 열. 앞의 규칙 열과 뒤의 비고 열은 빠짐.
        cols = [j for _, c in rows for j, cell in enumerate(c) if VERDICT.match(cell)]
        span = range(min(cols), max(cols) + 1) if cols else range(0)
        for rid, c in rows:
            seen.add(rid)
            if not any(VERDICT.match(cell) for cell in c):
                continue  # 판정 없는 행(규칙 목록 표 등)은 다른 표의 판정을 기다림
            blank = [j for j in span if j >= len(c) or c[j] in BLANK]
            if blank:
                bad[rid] = f"빈 판정 칸 {len(blank)}개"
            else:
                done.add(rid)
    judged = done - bad.keys()
    missing = [i for i in ids if i not in seen]
    undecided = [i for i in ids if i in seen and i not in judged]

    figure_text = "그림 규격 포함" if any(x["group"] == "LG" for x in items) else "그림 규격 미포함"
    print(f"점검표 항목 : {len(ids)}개({figure_text}), 위치 : {path}")
    print(f"판정한 번호 : {len(judged)}개")
    print(f"빠진 번호 : {len(missing)}개")
    for i in missing:
        print(f"  {i}  {ids[i]['text'][:40]}")
    print(f"미판정 번호 : {len(undecided)}개")
    for i in undecided:
        print(f"  {i}  ({bad.get(i, '판정 낱말 없음')}) {ids[i]['text'][:40]}")
    if unknown:
        print(f"점검표에 없는 번호(오타 확인) : {', '.join(sorted(unknown))}")
    if missing or undecided:
        print("검수 미완료")
        return 1
    print("누락 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
