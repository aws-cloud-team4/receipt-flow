"""The project's Markdown documents as a small search index for the public guide chat.

Sources are the repository docs (README, AGENTS, docs/*.md, deploy/README). Locally they are read from
the repository; in the container image the deploy pipeline copies them into `chat-service/guide_docs/`
(see deploy/copy-guide-docs.sh). Values that should not reach a public chat — account numbers, ARNs,
IAM user names, e-mail addresses — are masked before anything is indexed.

Search is a plain keyword score over Korean character bigrams (no extra AWS resource): a question
picks the few sections that share the most rare bigrams with it.
"""

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DOC_PATTERNS = ("README.md", "AGENTS.md", "deploy/README.md", "docs/*.md")
# Whole documents in reading order for the model (the full set is ~80k tokens; the request caches it).
FULL_ORDER = (
    "README.md",
    "docs/architecture.md",
    "docs/contract.md",
    "docs/ui.md",
    "docs/ai.md",
    "docs/backend.md",
    "docs/aws.md",
    "docs/worker.md",
    "docs/model-eval.md",
    "docs/local-setup.md",
    "deploy/README.md",
    "AGENTS.md",
)
SECTION_MAX = 2400  # characters; long sections are split so one answer does not pull in a whole file
CONTEXT_BUDGET = 7000  # characters of searched sections sent with one question (on top of the overview)
# Always sent: what the service is, the big picture, one receipt's path, roles (a broad question needs them).
OVERVIEW = (
    ("README.md", "receiptflow — "),
    ("docs/architecture.md", "1. 시스템 한 장 그림"),
    ("docs/architecture.md", "2. 영수증 한 장이 지나가는 길"),
    ("docs/architecture.md", "3. 역할과 화면"),
    ("docs/architecture.md", "5. 기술 선택 요약"),
)
# Question words carry no topic ("어떻게 쓰나요?" should match on 쓰다, not on 어떻게).
_STOP = set(
    "어떻 떻게 어떤 무엇 뭐예 뭘해 뭐야 무슨 누구 구예 구야 예요 에요 어요 아요 나요 하나 해요 돼요 되나 "
    "되요 있나 있어 인가 가요 까요 알려 려줘 려주 주세 세요 얼마 마나 하는 하고 해서 그럼 이거 그거 저거 "
    "우리 서비 비스 receiptflow 영수 수증".split()
)

_MASKS = (
    (re.compile(r"arn:aws:[^\s`\"')\]]+"), "[ARN]"),
    (re.compile(r"\b\d{12}\b"), "[계정]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[이메일]"),
    (re.compile(r"\b(chahee|junyoung|subin|taehee)\b"), "[IAM 사용자]"),
)
_WORD = re.compile(r"[0-9A-Za-z가-힣_]+")


@dataclass
class Section:
    file: str
    title: str
    text: str
    grams: Counter = field(default_factory=Counter)


def mask(text: str) -> str:
    for pattern, replacement in _MASKS:
        text = pattern.sub(replacement, text)
    return text


def grams(text: str) -> Counter:
    """Lower-cased words plus Korean character bigrams (particles stick to Korean words)."""
    out: Counter = Counter()
    for word in _WORD.findall(text.lower()):
        if len(word) >= 2:
            out[word] += 1
        if re.search(r"[가-힣]", word):
            out.update(word[i : i + 2] for i in range(len(word) - 1))
    for g in _STOP & set(out):
        del out[g]
    return out


def find_root() -> Path | None:
    """The folder holding the documents: RF_GUIDE_DOCS (the image's copy), else the repository."""
    configured = os.environ.get("RF_GUIDE_DOCS")
    if configured and (Path(configured) / "docs" / "architecture.md").is_file():
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "guide_docs", parent):
            if (candidate / "docs" / "architecture.md").is_file():
                return candidate
    return None


def split(file: str, text: str) -> list[Section]:
    sections: list[Section] = []
    heads: list[str] = []
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if not content:
            return
        title = " › ".join(heads) or file
        for i in range(0, len(content), SECTION_MAX):
            sections.append(Section(file, title, content[i : i + SECTION_MAX]))

    for line in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush()
            body = []
            level = len(m.group(1))
            heads = heads[: level - 1] + [m.group(2).strip()]
        else:
            body.append(line)
    flush()
    return sections


@lru_cache(maxsize=1)
def all_docs() -> str:
    """Every document, masked, in FULL_ORDER (then any other docs/*.md), each under a file header."""
    root = find_root()
    if not root:
        return ""
    others = sorted(p.relative_to(root).as_posix() for p in root.glob("docs/*.md"))
    names = list(FULL_ORDER) + [n for n in others if n not in FULL_ORDER]
    parts = [
        f"=== 파일: {name} ===\n" + mask((root / name).read_text(encoding="utf-8"))
        for name in names
        if (root / name).is_file()
    ]
    return "\n\n".join(parts)


@lru_cache(maxsize=1)
def index() -> tuple[list[Section], dict[str, float]]:
    root = find_root()
    sections: list[Section] = []
    if root:
        for pattern in DOC_PATTERNS:
            for path in sorted(root.glob(pattern)):
                rel = path.relative_to(root).as_posix()
                sections += split(rel, mask(path.read_text(encoding="utf-8")))
    for s in sections:
        s.grams = grams(s.title + " " + s.title + " " + s.text)  # the heading counts twice
    df: Counter = Counter()
    for s in sections:
        df.update(set(s.grams))
    n = max(1, len(sections))
    idf = {g: math.log(1 + n / c) for g, c in df.items()}
    return sections, idf


def overview() -> list[Section]:
    sections, _ = index()
    return [
        s for f, t in OVERVIEW for s in sections if s.file == f and s.title.split(" › ")[-1].startswith(t)
    ]


def search(question: str, budget: int = CONTEXT_BUDGET) -> list[Section]:
    """The best-matching sections within the character budget, best first (overview sections excluded)."""
    sections, idf = index()
    q = grams(question)
    if not q or not sections:
        return []
    base = {id(s) for s in overview()}
    scored = []
    for s in sections:
        if id(s) in base:
            continue
        score = sum(idf.get(g, 0.0) * min(c, s.grams[g]) for g, c in q.items() if g in s.grams)
        if score > 0:
            scored.append((score / math.sqrt(1 + len(s.text) / 800), s))
    scored.sort(key=lambda x: -x[0])
    picked, used = [], 0
    for _, s in scored:
        if used + len(s.text) > budget:
            continue
        picked.append(s)
        used += len(s.text)
        if len(picked) >= 8:
            break
    return picked
