"""Add a face-reframe switch to the verified, pinned Chopify revision."""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str, expected: int = 1) -> None:
    source = path.read_text(encoding="utf-8")
    if new in source:
        return
    if source.count(old) != expected:
        raise RuntimeError(f"Pinned Chopify source no longer matches expected patch point: {path.name}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def prepare(chopify_dir: Path) -> None:
    main = chopify_dir / "chopify.py"
    renderer = chopify_dir / "render_clips.py"
    scorer = chopify_dir / "score_clips.py"
    downloader = chopify_dir / "download_and_transcribe.py"
    replace_once(
        main,
        '    ap.add_argument("--loudnorm", action="store_true",\n                    help="normalize audio to -14 LUFS (platform standard)")\n',
        '    ap.add_argument("--loudnorm", action="store_true",\n                    help="normalize audio to -14 LUFS (platform standard)")\n'
        '    ap.add_argument("--no-face-reframe", action="store_true")\n',
    )
    replace_once(
        main,
        '    ap.add_argument("--max-clips", type=int, default=10)\n',
        '    ap.add_argument("--max-clips", type=int, default=10)\n'
        '    ap.add_argument("--allow-incomplete-thoughts", action="store_true")\n',
    )
    replace_once(
        main,
        '    if args.llm:\n        cmd += ["--llm", args.llm]\n',
        '    if args.llm:\n        cmd += ["--llm", args.llm]\n'
        '    if args.allow_incomplete_thoughts:\n        cmd.append("--allow-incomplete-thoughts")\n',
    )
    replace_once(
        main,
        '    if args.loudnorm:\n        cmd.append("--loudnorm")\n',
        '    if args.loudnorm:\n        cmd.append("--loudnorm")\n'
        '    if args.no_face_reframe:\n        cmd.append("--no-face-reframe")\n',
    )
    replace_once(
        renderer,
        '           do_tighten=False, loudnorm=False, preview=False):\n',
        '           do_tighten=False, loudnorm=False, preview=False, face_reframe=True):\n',
    )
    replace_once(renderer, '    needs_track = cw < W * 0.95',
                 '    needs_track = face_reframe and cw < W * 0.95')
    replace_once(
        renderer,
        '    ap.add_argument("--preview", action="store_true",\n',
        '    ap.add_argument("--no-face-reframe", action="store_true")\n'
        '    ap.add_argument("--preview", action="store_true",\n',
    )
    replace_once(
        renderer,
        '                                    preview=args.preview)))\n',
        '                                    preview=args.preview,\n'
        '                                    face_reframe=not args.no_face_reframe)))\n',
    )
    replace_once(
        scorer,
        'def _grow_window(sentences, seed, taken, min_len, max_len):\n',
        'def _grow_window(sentences, seed, taken, min_len, max_len, complete_thought=True):\n',
    )
    replace_once(
        scorer,
        '    while not is_arc_complete(sentences[j]["text"]) and j + 1 < n \\\n',
        '    while complete_thought and not is_arc_complete(sentences[j]["text"]) and j + 1 < n \\\n',
    )
    replace_once(scorer, '    while j > seed and not is_arc_complete(sentences[j]["text"]):\n',
                 '    while complete_thought and j > seed and not is_arc_complete(sentences[j]["text"]):\n')
    replace_once(scorer, '    if not is_arc_complete(sentences[j]["text"]):\n',
                 '    if complete_thought and not is_arc_complete(sentences[j]["text"]):\n')
    replace_once(
        scorer,
        'def build_candidates(sentences, min_len, max_len, max_clips):\n',
        'def build_candidates(sentences, min_len, max_len, max_clips, complete_thought=True):\n',
    )
    replace_once(scorer, '        w = _grow_window(sentences, seed, taken, min_len, max_len)\n',
                 '        w = _grow_window(sentences, seed, taken, min_len, max_len, complete_thought)\n',
                 expected=2)
    replace_once(
        scorer,
        'def search_candidates(sentences, query, min_len, max_len, max_clips):\n',
        'def search_candidates(sentences, query, min_len, max_len, max_clips, complete_thought=True):\n',
    )
    replace_once(
        scorer,
        'def run(workdir, llm=None, host=OLLAMA_HOST, min_score=None, max_clips=10,\n'
        '        min_len=20, max_len=75, search=None, pick=None):\n',
        'def run(workdir, llm=None, host=OLLAMA_HOST, min_score=None, max_clips=10,\n'
        '        min_len=20, max_len=75, search=None, pick=None, complete_thought=True):\n',
    )
    replace_once(scorer, '        segments = search_candidates(sentences, search, min_len, max_len, max_clips)\n',
                 '        segments = search_candidates(sentences, search, min_len, max_len, max_clips, complete_thought)\n')
    replace_once(scorer, '        segments = build_candidates(sentences, min_len, max_len, max_clips)\n',
                 '        segments = build_candidates(sentences, min_len, max_len, max_clips, complete_thought)\n')
    replace_once(scorer, '        segments = build_candidates(sentences, min_len, max_len, 1)\n',
                 '        segments = build_candidates(sentences, min_len, max_len, 1, complete_thought)\n')
    replace_once(
        scorer,
        '    ap.add_argument("--max-clips", type=int, default=10)\n',
        '    ap.add_argument("--max-clips", type=int, default=10)\n'
        '    ap.add_argument("--allow-incomplete-thoughts", action="store_true")\n',
    )
    replace_once(
        scorer,
        '        args.min_len, args.max_len, search=args.search, pick=args.clips)\n',
        '        args.min_len, args.max_len, search=args.search, pick=args.clips,\n'
        '        complete_thought=not args.allow_incomplete_thoughts)\n',
    )
    replace_once(
        downloader,
        '        "--no-playlist",\n',
        '        "--no-playlist", "--retries", "5", "--fragment-retries", "5",\n'
        '        "--extractor-retries", "3",\n',
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("chopify_dir", type=Path)
    args = parser.parse_args()
    prepare(args.chopify_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())