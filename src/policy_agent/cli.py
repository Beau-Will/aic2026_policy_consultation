"""命令行入口：`policy-agent <command>`。

本地：import / search / stats / brief
接入：validate / acs / register / serve / preflight
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

WHEEL_DIR = Path("vendor/wheels")
EXPECTED_SDK = "2.2.0"
EXPECTED_WIT = "2.1.0"


def _apply_db_override(db: str | None) -> None:
    if db:
        os.environ["POLICY_CORPUS_DB"] = db


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


# --------------------------------------------------------------------- import
def cmd_import(args: argparse.Namespace) -> int:
    from .corpus.importer import build_document
    from .corpus.store import get_store

    store = get_store()
    if getattr(args, "reset", False):
        store.reset()
        print("[重建] 已清空语料库，将重新导入全部文件。")
    total_docs = 0
    total_articles = 0
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            from .corpus.importer import iter_supported_files

            files = iter_supported_files(path)
        else:
            files = [path]
        for file in files:
            single = len(files) == 1
            title = args.title if (args.title and single) else None
            doc_id = args.doc_id if (args.doc_id and single) else None
            try:
                doc = build_document(
                    file,
                    doc_id=doc_id,
                    title=title,
                    issuer=args.issuer,
                    doc_number=args.doc_number,
                    publish_date=args.publish_date,
                    effective_date=args.effective_date,
                    region=args.region,
                    source_url=args.source_url,
                )
            except Exception as exc:  # noqa: BLE001 - CLI 需给出逐文件错误
                print(f"[跳过] {file}: {exc}", file=sys.stderr)
                continue
            existed = store.has_document(doc.doc_id)
            count = store.add_document(doc)
            total_docs += 1
            total_articles += count
            action = "更新" if existed else "新增"
            print(f"[{action}] {file} -> doc_id={doc.doc_id} 条文={count} 标题={doc.title}")
    print(f"完成：{total_docs} 份文档，{total_articles} 条条文。库统计={store.stats()}")
    return 0


# --------------------------------------------------------------------- search
def cmd_search(args: argparse.Namespace) -> int:
    from .corpus.store import get_store

    hits = get_store().search(args.query, limit=args.limit)
    if args.json:
        _print_json({"query": args.query, "count": len(hits), "hits": hits})
        return 0
    if not hits:
        print("未找到匹配条文。")
        return 1
    for i, hit in enumerate(hits, start=1):
        label = " ".join(x for x in (hit["chapter_path"], hit["article_no"]) if x) or hit["citation_id"]
        print(f"{i}. [{label}] {hit['doc_title']}")
        print(f"   citation_id: {hit['citation_id']}")
        print(f"   {hit['snippet']}")
        print()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from .corpus.store import get_store

    _print_json(get_store().stats())
    return 0


# ---------------------------------------------------------------------- brief
def _extract_brief(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(observations):
        payload = item.get("result", item) if isinstance(item, dict) else None
        if isinstance(payload, dict) and "brief" in payload:
            return payload
    return None


def cmd_brief(args: argparse.Namespace) -> int:
    from wit import RunConfig

    from .serving import build_runtime

    async def _run() -> tuple[str, list[dict[str, Any]]]:
        handle = build_runtime(required_provider=True)
        try:
            result = await handle.runtime.run(args.query, RunConfig(max_steps=args.max_steps))
            return result.final_text or "", list(result.observations)
        finally:
            await handle.aclose()

    markdown, observations = asyncio.run(_run())
    print(markdown)
    structured = _extract_brief(observations)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"\n[已写出 Markdown] {args.out}")
    if args.json:
        out_path = Path(args.json)
        payload = structured or {"observations": observations}
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(f"[已写出 JSON] {out_path}")
    return 0


# ------------------------------------------------------------------- 接入相关
def cmd_validate(args: argparse.Namespace) -> int:
    from .serving import validate_agent

    report = validate_agent()
    _print_json(report)
    return 0 if report["valid"] else 2


def cmd_acs(args: argparse.Namespace) -> int:
    from .serving import save_acs_draft

    path = save_acs_draft(path=args.out)
    print(f"ACS 草稿已写入：{path}")
    print(Path(path).read_text(encoding="utf-8"))
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    from .serving import register

    _print_json(asyncio.run(register()))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .serving import serve

    try:
        payload = asyncio.run(serve(block=not args.no_block))
    except KeyboardInterrupt:
        print("\n已停止。")
        return 0
    _print_json(payload)
    return 0


# -------------------------------------------------------------------- preflight
def cmd_preflight(args: argparse.Namespace) -> int:
    checks: list[dict[str, Any]] = []
    ok = True

    for name, expected in (("acps-sdk", EXPECTED_SDK), ("wit-framework", EXPECTED_WIT)):
        try:
            actual = version(name)
            passed = actual == expected
            checks.append({"check": f"{name} 版本", "expected": expected, "actual": actual, "ok": passed})
            ok = ok and passed
        except Exception as exc:  # noqa: BLE001
            checks.append({"check": f"{name} 版本", "expected": expected, "error": str(exc), "ok": False})
            ok = False

    try:
        import acps_sdk
        import wit

        site_ok = "site-packages" in str(acps_sdk.__file__) and "site-packages" in str(wit.__file__)
        checks.append(
            {
                "check": "导入来源",
                "acps_sdk": str(acps_sdk.__file__),
                "wit": str(wit.__file__),
                "ok": site_ok,
            }
        )
        ok = ok and site_ok
    except Exception as exc:  # noqa: BLE001
        checks.append({"check": "导入来源", "error": str(exc), "ok": False})
        ok = False

    sums_file = WHEEL_DIR / "SHA256SUMS"
    if sums_file.exists():
        for line in sums_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            digest, _, filename = line.partition("  ")
            wheel = WHEEL_DIR / filename.strip()
            if not wheel.exists():
                checks.append({"check": f"wheel {filename}", "ok": False, "error": "缺失"})
                ok = False
                continue
            actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
            passed = actual == digest.strip()
            checks.append({"check": f"wheel {filename}", "ok": passed, "sha256": actual})
            ok = ok and passed
    else:
        checks.append({"check": "SHA256SUMS", "ok": False, "error": "未找到 vendor/wheels/SHA256SUMS"})
        ok = False

    _print_json({"ok": ok, "checks": checks})
    return 0 if ok else 2


# ----------------------------------------------------------------------- 装配
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="policy-agent",
        description="官方政策执行解读智能体（本地语料 + wit/ACPs Partner）",
    )
    parser.add_argument("--db", help="覆盖语料库路径（默认 POLICY_CORPUS_DB / data/corpus.db）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="导入权威原文（md/txt/html/pdf/docx，支持目录）")
    p.add_argument("paths", nargs="+")
    p.add_argument("--doc-id", help="显式指定 doc_id（单文件时生效；重复导入同名 doc_id 会覆盖）")
    p.add_argument("--reset", action="store_true", help="先清空整个语料库再导入（重建索引）")
    p.add_argument("--title")
    p.add_argument("--issuer")
    p.add_argument("--doc-number")
    p.add_argument("--publish-date")
    p.add_argument("--effective-date")
    p.add_argument("--region")
    p.add_argument("--source-url")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("search", help="本地条文级检索")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("stats", help="查看语料库统计")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("brief", help="本地运行智能体，生成执行说明（需 API Key）")
    p.add_argument("query")
    p.add_argument("--out", help="把 Markdown 写入文件")
    p.add_argument("--json", help="把结构化 ExecutionBrief 写入文件")
    p.add_argument("--max-steps", type=int, default=12)
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("validate", help="本地校验 Agent 编译结果与能力投影")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("acs", help="生成 ACS 草稿")
    p.add_argument("--out", help="输出路径")
    p.set_defaults(func=cmd_acs)

    p = sub.add_parser("register", help="推进 ACPs 注册（可能停在待审核）")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("serve", help="注册到位后启动 Direct Partner listener")
    p.add_argument("--no-block", action="store_true", help="启动后立即返回，不阻塞")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("preflight", help="校验 wit/acps-sdk 版本、导入来源与 wheel 校验和")
    p.set_defaults(func=cmd_preflight)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_db_override(getattr(args, "db", None))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
